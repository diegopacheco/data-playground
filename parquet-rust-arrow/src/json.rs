use crate::aggregate::CategoryAgg;
use crate::lake::{PROJECTED, Scan};
use crate::metadata::{ColumnInfo, FileInfo, RowGroupInfo};

pub fn aggregates(from: Option<&str>, scan: &Scan, rows: &[CategoryAgg]) -> String {
    let items: Vec<String> = rows
        .iter()
        .map(|a| {
            format!(
                r#"{{"category":{},"orders":{},"quantity":{},"revenue":{:.2},"avg_price":{:.2},"min_price":{:.2},"max_price":{:.2}}}"#,
                text(&a.category),
                a.orders,
                a.quantity,
                a.revenue,
                a.avg_price,
                a.min_price,
                a.max_price
            )
        })
        .collect();
    format!(
        r#"{{"from":{},"projection":[{}],"row_groups_total":{},"row_groups_read":[{}],"rows_read":{},"aggregates":[{}]}}"#,
        from.map(text).unwrap_or_else(|| "null".to_string()),
        PROJECTED.iter().map(|c| text(c)).collect::<Vec<_>>().join(","),
        scan.row_groups_total,
        scan.row_groups_read.iter().map(|i| i.to_string()).collect::<Vec<_>>().join(","),
        scan.rows_read,
        items.join(",")
    )
}

pub fn metadata(file: &str, info: &FileInfo) -> String {
    format!(
        r#"{{"file":{},"file_bytes":{},"num_rows":{},"created_by":{},"row_groups":[{}]}}"#,
        text(file),
        info.file_bytes,
        info.num_rows,
        text(&info.created_by),
        info.row_groups.iter().map(row_group).collect::<Vec<_>>().join(",")
    )
}

fn row_group(rg: &RowGroupInfo) -> String {
    format!(
        r#"{{"rows":{},"uncompressed_bytes":{},"compressed_bytes":{},"columns":[{}]}}"#,
        rg.rows,
        rg.uncompressed_bytes,
        rg.compressed_bytes,
        rg.columns.iter().map(column).collect::<Vec<_>>().join(",")
    )
}

fn column(c: &ColumnInfo) -> String {
    format!(
        r#"{{"name":{},"physical_type":{},"compression":{},"encodings":[{}],"compressed_bytes":{},"uncompressed_bytes":{},"min":{},"max":{},"nulls":{}}}"#,
        text(&c.name),
        text(&c.physical_type),
        text(&c.compression),
        c.encodings.iter().map(|e| text(e)).collect::<Vec<_>>().join(","),
        c.compressed_bytes,
        c.uncompressed_bytes,
        text(&c.min),
        text(&c.max),
        c.nulls.map(|n| n.to_string()).unwrap_or_else(|| "null".to_string())
    )
}

pub fn text(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('"');
    for ch in s.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}
