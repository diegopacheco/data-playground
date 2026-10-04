use crate::codec::Values;
use crate::data::Column;
use crate::json::q;
use std::io::Write;
use std::process::{Command, Stdio};

fn bin() -> String {
    std::env::var("DUCKDB_BIN").unwrap_or_else(|_| "duckdb".into())
}

pub fn version() -> String {
    Command::new(bin()).arg("--version").output().map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string()).unwrap_or_else(|_| "missing".into())
}

fn csv(v: &Values) -> String {
    let mut out = String::new();
    match v {
        Values::Int(x) => x.iter().for_each(|i| { out.push_str(&i.to_string()); out.push('\n'); }),
        Values::Float(x) => x.iter().for_each(|f| { out.push_str(&f.to_string()); out.push('\n'); }),
        Values::Str(x) => x.iter().for_each(|s| { out.push('"'); out.push_str(&s.replace('"', "\"\"")); out.push_str("\"\n"); }),
    }
    out
}

fn sql(v: &Values, base: &str) -> String {
    let (ty, check) = match v {
        Values::Int(_) => ("BIGINT", "sum(v)::VARCHAR"),
        Values::Float(_) => ("DOUBLE", "sum(round(v * 100)::BIGINT)::VARCHAR"),
        Values::Str(_) => ("VARCHAR", "sum(strlen(v))::VARCHAR"),
    };
    let parquet = |tag: &str, opts: &str| {
        format!(
            "COPY t TO '{b}-{t}.parquet' (FORMAT parquet, {o});\nSELECT '{t}', string_agg(DISTINCT encodings, ' + '), sum(total_compressed_size) FROM parquet_metadata('{b}-{t}.parquet');\n",
            b = base, t = tag, o = opts
        )
    };
    format!(
        ".mode list\n.separator |\n.headers off\nSET threads = 2;\nSET memory_limit = '512MB';\n\
         CREATE TABLE t AS SELECT * FROM read_csv('{b}.csv', header = false, columns = {{'v': '{ty}'}}, delim = ',', quote = '\"', escape = '\"');\n\
         CHECKPOINT;\n\
         SELECT 'storage', compression, count(*) FROM pragma_storage_info('t') WHERE segment_type <> 'VALIDITY' GROUP BY compression ORDER BY 3 DESC, 2;\n\
         SELECT 'size', used_blocks * block_size FROM pragma_database_size();\n\
         SELECT 'check', count(*), {check} FROM t;\n{p1}{p2}{p3}",
        b = base, ty = ty, check = check,
        p1 = parquet("v1", "COMPRESSION uncompressed"),
        p2 = parquet("v2", "COMPRESSION uncompressed, PARQUET_VERSION v2"),
        p3 = parquet("zstd", "COMPRESSION zstd")
    )
}

pub fn analyze(c: &Column, work: &str) -> Result<String, String> {
    std::fs::create_dir_all(work).map_err(|e| e.to_string())?;
    let base = format!("{}/{}", work, c.name);
    let db = format!("{}.duckdb", base);
    for f in [db.clone(), format!("{}.duckdb.wal", base)] {
        let _ = std::fs::remove_file(f);
    }
    std::fs::write(format!("{}.csv", base), csv(&c.values)).map_err(|e| e.to_string())?;
    let mut child = Command::new(bin()).arg("-bail").arg(&db).stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().map_err(|e| format!("cannot run duckdb: {}", e))?;
    child.stdin.take().unwrap().write_all(sql(&c.values, &base).as_bytes()).map_err(|e| e.to_string())?;
    let out = child.wait_with_output().map_err(|e| e.to_string())?;
    if !out.status.success() {
        return Err(format!("duckdb failed on {}: {}", c.name, String::from_utf8_lossy(&out.stderr)));
    }
    let text = String::from_utf8_lossy(&out.stdout).to_string();
    let rows: Vec<Vec<&str>> = text.lines().map(|l| l.split('|').collect()).collect();
    let get = |tag: &str| rows.iter().find(|r| r[0] == tag).cloned().ok_or(format!("duckdb output missing {} for {}", tag, c.name));
    let storage: Vec<String> = rows.iter().filter(|r| r[0] == "storage").map(|r| format!("{{\"compression\":{},\"segments\":{}}}", q(r[1]), r[2])).collect();
    let pq = |tag: &str| get(tag).map(|r| format!("{{\"encodings\":{},\"bytes\":{}}}", q(r[1]), r[2]));
    let check = get("check")?;
    Ok(format!(
        "{{\"storage\":[{}],\"db_bytes\":{},\"count\":{},\"checksum\":{},\"parquet_v1\":{},\"parquet_v2\":{},\"parquet_zstd\":{}}}",
        storage.join(","), get("size")?[1], check[1], q(check[2]), pq("v1")?, pq("v2")?, pq("zstd")?
    ))
}
