use crate::codec::{decode, encode, encodings, Values};
use crate::data::Column;
use crate::duck;
use crate::json::{hex, list, num, q};
use std::time::Instant;

const RUNS: usize = 3;

pub struct Measure {
    pub encoding: &'static str,
    pub bytes: usize,
    pub encode_ms: f64,
    pub decode_ms: f64,
    pub roundtrip: bool,
    pub detail: String,
    pub head: Vec<u8>,
}

fn best_ms<T>(f: impl Fn() -> T) -> (T, f64) {
    let mut best = f64::MAX;
    let mut last = None;
    for _ in 0..RUNS {
        let t = Instant::now();
        let out = f();
        best = best.min(t.elapsed().as_secs_f64() * 1000.0);
        last = Some(out);
    }
    (last.unwrap(), best)
}

pub fn measure(encoding: &'static str, v: &Values) -> Result<Measure, String> {
    let (enc, encode_ms) = best_ms(|| encode(encoding, v));
    let enc = enc?;
    let (dec, decode_ms) = best_ms(|| decode(encoding, v.kind(), &enc.bytes));
    let roundtrip = dec.map(|d| v.same(&d)).unwrap_or(false);
    Ok(Measure { encoding, bytes: enc.bytes.len(), encode_ms, decode_ms, roundtrip, detail: enc.detail, head: enc.bytes[..enc.bytes.len().min(48)].to_vec() })
}

fn mbs(raw: usize, ms: f64) -> f64 {
    raw as f64 / 1e6 / (ms.max(1e-6) / 1000.0)
}

fn sample(v: &Values) -> Vec<String> {
    match v {
        Values::Int(x) => x.iter().take(6).map(|i| i.to_string()).collect(),
        Values::Float(x) => x.iter().take(6).map(|f| f.to_string()).collect(),
        Values::Str(x) => x.iter().take(6).cloned().collect(),
    }
}

fn column_json(c: &Column, duck_json: &str) -> Result<String, String> {
    let raw = c.values.raw_bytes();
    let rows: Vec<Measure> = encodings(c.values.kind()).iter().map(|e| measure(e, &c.values)).collect::<Result<_, _>>()?;
    let best = rows.iter().filter(|m| m.roundtrip).min_by_key(|m| m.bytes).map(|m| m.encoding).unwrap_or("none");
    let encs = list(&rows, |m| {
        format!(
            "{{\"name\":{},\"bytes\":{},\"ratio\":{},\"encode_ms\":{},\"decode_ms\":{},\"encode_mbs\":{},\"decode_mbs\":{},\"roundtrip\":{},\"detail\":{},\"head_hex\":{}}}",
            q(m.encoding), m.bytes, num(raw as f64 / m.bytes.max(1) as f64), num(m.encode_ms), num(m.decode_ms),
            num(mbs(raw, m.encode_ms)), num(mbs(raw, m.decode_ms)), m.roundtrip, q(&m.detail), q(&hex(&m.head))
        )
    });
    Ok(format!(
        "{{\"name\":{},\"about\":{},\"type\":{},\"rows\":{},\"raw_bytes\":{},\"best\":{},\"sample\":{},\"encodings\":{},\"duckdb\":{}}}",
        q(c.name), q(c.about), q(c.values.kind()), c.values.len(), raw, q(best), list(&sample(&c.values), |s| q(s)), encs, duck_json
    ))
}

pub fn run(cols: &[Column], work: &str) -> Result<String, String> {
    let started = Instant::now();
    let mut parts = Vec::new();
    for c in cols {
        let d = duck::analyze(c, work)?;
        let json = column_json(c, &d)?;
        println!("measured {} in {:.1}s", c.name, started.elapsed().as_secs_f64());
        parts.push(json);
    }
    let unix = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
    Ok(format!(
        "{{\"generated_unix\":{},\"rows\":{},\"runs\":{},\"duckdb_version\":{},\"elapsed_s\":{},\"columns\":[{}]}}",
        unix, cols.first().map(|c| c.values.len()).unwrap_or(0), RUNS, q(&duck::version()), num(started.elapsed().as_secs_f64()), parts.join(",")
    ))
}
