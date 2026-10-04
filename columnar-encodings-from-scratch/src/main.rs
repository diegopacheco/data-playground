mod bench;
mod bits;
mod codec;
mod data;
mod duck;
mod json;

use codec::{decode, encode, encodings, Values};
use data::Column;
use json::{hex, list, q, unhex};
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

const INDEX: &str = include_str!("../web/index.html");
const MAX_BODY: usize = 64 << 20;

struct State {
    columns: Vec<Column>,
    results: Mutex<Option<String>>,
    error: Mutex<Option<String>>,
    running: AtomicBool,
    work: String,
}

struct Reply {
    status: u16,
    kind: &'static str,
    body: String,
}

fn reply(status: u16, body: String) -> Reply {
    Reply { status, kind: "application/json", body }
}

fn fail(status: u16, msg: &str) -> Reply {
    reply(status, format!("{{\"error\":{}}}", q(msg)))
}

fn env_or(key: &str, default: &str) -> String {
    std::env::var(key).unwrap_or_else(|_| default.into())
}

fn main() {
    let rows: usize = env_or("ROWS", "1000000").parse().expect("ROWS must be a number");
    let port = env_or("PORT", "8080");
    let state = Arc::new(State { columns: data::generate(rows), results: Mutex::new(None), error: Mutex::new(None), running: AtomicBool::new(false), work: env_or("WORK_DIR", "/tmp/r18") });
    println!("generated {} columns of {} rows", state.columns.len(), rows);
    start_bench(&state);
    let listener = TcpListener::bind(format!("0.0.0.0:{}", port)).expect("cannot bind port");
    println!("listening on {}", port);
    for stream in listener.incoming().flatten() {
        let st = state.clone();
        std::thread::spawn(move || {
            if let Err(e) = handle(stream, &st) {
                eprintln!("request failed: {}", e);
            }
        });
    }
}

fn start_bench(state: &Arc<State>) -> bool {
    if state.running.swap(true, Ordering::SeqCst) {
        return false;
    }
    let st = state.clone();
    std::thread::spawn(move || {
        match bench::run(&st.columns, &st.work) {
            Ok(json) => {
                *st.results.lock().unwrap() = Some(json);
                *st.error.lock().unwrap() = None;
            }
            Err(e) => {
                eprintln!("benchmark failed: {}", e);
                *st.error.lock().unwrap() = Some(e);
            }
        }
        st.running.store(false, Ordering::SeqCst);
    });
    true
}

fn handle(stream: TcpStream, state: &Arc<State>) -> Result<(), String> {
    let mut r = BufReader::new(stream.try_clone().map_err(|e| e.to_string())?);
    let mut line = String::new();
    r.read_line(&mut line).map_err(|e| e.to_string())?;
    let mut parts = line.split_whitespace();
    let (method, target) = (parts.next().unwrap_or("").to_string(), parts.next().unwrap_or("/").to_string());
    let mut length = 0usize;
    loop {
        let mut h = String::new();
        if r.read_line(&mut h).map_err(|e| e.to_string())? == 0 || h.trim().is_empty() {
            break;
        }
        if let Some((k, v)) = h.split_once(':') {
            if k.trim().eq_ignore_ascii_case("content-length") {
                length = v.trim().parse().unwrap_or(0);
            }
        }
    }
    let out = if length > MAX_BODY {
        fail(413, "body too large")
    } else {
        let mut body = vec![0u8; length];
        r.read_exact(&mut body).map_err(|e| e.to_string())?;
        route(&method, &target, &body, state)
    };
    let reason = match out.status { 200 => "OK", 202 => "Accepted", 400 => "Bad Request", 404 => "Not Found", 413 => "Payload Too Large", 500 => "Internal Server Error", _ => "Service Unavailable" };
    let mut w = stream;
    write!(w, "HTTP/1.1 {} {}\r\nContent-Type: {}\r\nContent-Length: {}\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n", out.status, reason, out.kind, out.body.len()).map_err(|e| e.to_string())?;
    w.write_all(out.body.as_bytes()).map_err(|e| e.to_string())
}

fn query<'a>(target: &'a str, key: &str) -> Option<&'a str> {
    target.split_once('?')?.1.split('&').filter_map(|kv| kv.split_once('=')).find(|(k, _)| *k == key).map(|(_, v)| v)
}

fn route(method: &str, target: &str, body: &[u8], state: &Arc<State>) -> Reply {
    let path = target.split('?').next().unwrap_or("/");
    match (method, path) {
        ("GET", "/") => Reply { status: 200, kind: "text/html; charset=utf-8", body: INDEX.into() },
        ("GET", "/api/health") => reply(200, "{\"status\":\"UP\"}".into()),
        ("GET", "/api/results") => results(state),
        ("POST", "/api/run") => {
            let started = start_bench(state);
            reply(202, format!("{{\"started\":{}}}", started))
        }
        ("GET", "/api/columns") => reply(200, list(&state.columns, |c| format!("{{\"name\":{},\"type\":{},\"rows\":{},\"about\":{}}}", q(c.name), q(c.values.kind()), c.values.len(), q(c.about)))),
        ("POST", "/api/roundtrip") => match roundtrip(target, body) {
            Ok(b) => reply(200, b),
            Err(e) => fail(400, &e),
        },
        ("GET", p) if p.starts_with("/api/column/") && p.ends_with("/values") => {
            let name = &p["/api/column/".len()..p.len() - "/values".len()];
            let limit = query(target, "limit").and_then(|l| l.parse().ok()).unwrap_or(usize::MAX);
            match state.columns.iter().find(|c| c.name == name) {
                Some(c) => reply(200, values_json(&c.values, limit)),
                None => fail(404, "unknown column"),
            }
        }
        _ => fail(404, "not found"),
    }
}

fn results(state: &Arc<State>) -> Reply {
    if let Some(e) = state.error.lock().unwrap().clone() {
        return fail(500, &e);
    }
    match state.results.lock().unwrap().clone() {
        Some(r) if !state.running.load(Ordering::SeqCst) => reply(200, r),
        _ => fail(503, "benchmark running"),
    }
}

fn values_json(v: &Values, limit: usize) -> String {
    match v {
        Values::Int(x) => list(&x[..x.len().min(limit)], |i| i.to_string()),
        Values::Float(x) => list(&x[..x.len().min(limit)], |f| f.to_string()),
        Values::Str(x) => list(&x[..x.len().min(limit)], |s| q(s)),
    }
}

fn parse_values(kind: &str, lines: &[&str]) -> Result<Values, String> {
    let bad = |t: &str| format!("cannot parse {} as {}", t, kind);
    Ok(match kind {
        "int" => Values::Int(lines.iter().map(|t| t.trim().parse().map_err(|_| bad(t))).collect::<Result<_, _>>()?),
        "float" => Values::Float(lines.iter().map(|t| {
            let t = t.trim();
            match t.strip_prefix("0x") {
                Some(h) => u64::from_str_radix(h, 16).map(f64::from_bits).map_err(|_| bad(t)),
                None => t.parse().map_err(|_| bad(t)),
            }
        }).collect::<Result<_, _>>()?),
        "str" => Values::Str(lines.iter().map(|t| unhex(t.trim()).and_then(|b| String::from_utf8(b).map_err(|e| e.to_string()))).collect::<Result<_, _>>()?),
        _ => return Err("type must be int, float or str".into()),
    })
}

fn tokens(v: &Values) -> String {
    match v {
        Values::Int(x) => list(x, |i| q(&i.to_string())),
        Values::Float(x) => list(x, |f| q(&format!("0x{:016x}", f.to_bits()))),
        Values::Str(x) => list(x, |s| q(&hex(s.as_bytes()))),
    }
}

fn roundtrip(target: &str, body: &[u8]) -> Result<String, String> {
    let kind = query(target, "type").ok_or("missing type")?;
    let text = std::str::from_utf8(body).map_err(|e| e.to_string())?;
    let mut lines = text.split('\n');
    let n: usize = lines.next().unwrap_or("").trim().parse().map_err(|_| "first line must be the value count")?;
    let rest: Vec<&str> = lines.take(n).collect();
    if rest.len() != n {
        return Err(format!("expected {} values, got {}", n, rest.len()));
    }
    let v = parse_values(kind, &rest)?;
    let wanted: Vec<&str> = match query(target, "encoding") {
        Some(e) => vec![e],
        None => encodings(kind).to_vec(),
    };
    let mut out = Vec::new();
    for e in wanted {
        let enc = encode(e, &v)?;
        let dec = decode(e, kind, &enc.bytes)?;
        out.push(format!(
            "{{\"encoding\":{},\"encoded_bytes\":{},\"roundtrip\":{},\"detail\":{},\"head_hex\":{},\"values\":{}}}",
            q(e), enc.bytes.len(), v.same(&dec), q(&enc.detail), q(&hex(&enc.bytes[..enc.bytes.len().min(48)])), tokens(&dec)
        ));
    }
    Ok(format!("{{\"type\":{},\"n\":{},\"raw_bytes\":{},\"results\":[{}]}}", q(kind), n, v.raw_bytes(), out.join(",")))
}
