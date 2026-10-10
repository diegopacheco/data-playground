use std::env;
use std::error::Error;
use std::io::{BufRead, BufReader, Write};
use std::net::{TcpListener, TcpStream};
use std::path::Path;

use parquet_rust_arrow::{aggregate, build_lake, day_start_ms, json, lake, metadata};

const CSV: &str = "data/orders.csv";
const PARQUET: &str = "data/lake/orders.parquet";
const INDEX: &str = include_str!("../static/index.html");

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<String> = env::args().skip(1).collect();
    let bytes = build_lake(Path::new(CSV), Path::new(PARQUET))?;
    eprintln!("wrote {PARQUET} ({bytes} bytes)");
    match args.first().map(String::as_str) {
        Some("aggregates") => print_aggregates(args.get(1).map(String::as_str)),
        _ => serve(),
    }
}

fn print_aggregates(day: Option<&str>) -> Result<(), Box<dyn Error>> {
    let scan = lake::scan(Path::new(PARQUET), day.map(day_start_ms).transpose()?)?;
    eprintln!("row groups read {:?} of {}, rows read {}", scan.row_groups_read, scan.row_groups_total, scan.rows_read);
    for a in aggregate::by_category(&scan.batches)? {
        println!("{},{},{},{:.2}", a.category, a.orders, a.quantity, a.revenue);
    }
    Ok(())
}

fn serve() -> Result<(), Box<dyn Error>> {
    let port = env::var("PORT").unwrap_or_else(|_| "21280".to_string());
    let listener = TcpListener::bind(format!("0.0.0.0:{port}"))?;
    eprintln!("listening on http://localhost:{port}");
    for stream in listener.incoming() {
        if let Err(e) = stream.map_err(Into::into).and_then(handle) {
            eprintln!("request failed: {e}");
        }
    }
    Ok(())
}

fn handle(mut stream: TcpStream) -> Result<(), Box<dyn Error>> {
    let mut reader = BufReader::new(stream.try_clone()?);
    let mut request = String::new();
    reader.read_line(&mut request)?;
    let mut line = String::new();
    while reader.read_line(&mut line)? > 2 {
        line.clear();
    }
    let target = request.split_whitespace().nth(1).unwrap_or("/");
    let (path, query) = target.split_once('?').unwrap_or((target, ""));
    let (status, kind, body) = match route(path, query) {
        Ok(Some((kind, body))) => ("200 OK", kind, body),
        Ok(None) => ("404 Not Found", "application/json", r#"{"error":"not found"}"#.to_string()),
        Err(e) => ("400 Bad Request", "application/json", format!(r#"{{"error":{}}}"#, json::text(&e.to_string()))),
    };
    write!(
        stream,
        "HTTP/1.1 {status}\r\nContent-Type: {kind}; charset=utf-8\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    )?;
    Ok(())
}

fn route(path: &str, query: &str) -> Result<Option<(&'static str, String)>, Box<dyn Error>> {
    match path {
        "/" | "/index.html" => Ok(Some(("text/html", INDEX.to_string()))),
        "/api/aggregates" => {
            let from = param(query, "from");
            let scan = lake::scan(Path::new(PARQUET), from.map(day_start_ms).transpose()?)?;
            let rows = aggregate::by_category(&scan.batches)?;
            Ok(Some(("application/json", json::aggregates(from, &scan, &rows))))
        }
        "/api/metadata" => Ok(Some(("application/json", json::metadata(PARQUET, &metadata::read(Path::new(PARQUET))?)))),
        _ => Ok(None),
    }
}

fn param<'a>(query: &'a str, name: &str) -> Option<&'a str> {
    query
        .split('&')
        .filter_map(|kv| kv.split_once('='))
        .find(|(k, v)| *k == name && !v.is_empty())
        .map(|(_, v)| v)
}
