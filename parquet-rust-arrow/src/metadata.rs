use std::error::Error;
use std::fs::{self, File};
use std::path::Path;

use arrow::temporal_conversions::timestamp_ms_to_datetime;
use parquet::basic::LogicalType;
use parquet::file::metadata::{ColumnChunkMetaData, ParquetMetaDataReader};
use parquet::file::statistics::Statistics;

pub struct FileInfo {
    pub file_bytes: u64,
    pub num_rows: i64,
    pub created_by: String,
    pub row_groups: Vec<RowGroupInfo>,
}

pub struct RowGroupInfo {
    pub rows: i64,
    pub uncompressed_bytes: i64,
    pub compressed_bytes: i64,
    pub columns: Vec<ColumnInfo>,
}

pub struct ColumnInfo {
    pub name: String,
    pub physical_type: String,
    pub compression: String,
    pub encodings: Vec<String>,
    pub compressed_bytes: i64,
    pub uncompressed_bytes: i64,
    pub min: String,
    pub max: String,
    pub nulls: Option<u64>,
}

pub fn read(path: &Path) -> Result<FileInfo, Box<dyn Error>> {
    let meta = ParquetMetaDataReader::new().parse_and_finish(&File::open(path)?)?;
    let file = meta.file_metadata();
    let row_groups = meta
        .row_groups()
        .iter()
        .map(|rg| RowGroupInfo {
            rows: rg.num_rows(),
            uncompressed_bytes: rg.total_byte_size(),
            compressed_bytes: rg.compressed_size(),
            columns: rg.columns().iter().map(column_info).collect(),
        })
        .collect();
    Ok(FileInfo {
        file_bytes: fs::metadata(path)?.len(),
        num_rows: file.num_rows(),
        created_by: file.created_by().unwrap_or("").to_string(),
        row_groups,
    })
}

fn column_info(column: &ColumnChunkMetaData) -> ColumnInfo {
    let descr = column.column_descr();
    let timestamp = matches!(descr.logical_type_ref(), Some(LogicalType::Timestamp { .. }));
    let (min, max) = column.statistics().map(|s| bounds(s, timestamp)).unwrap_or_default();
    ColumnInfo {
        name: descr.name().to_string(),
        physical_type: descr.physical_type().to_string(),
        compression: column.compression().to_string().split('(').next().unwrap_or("").to_string(),
        encodings: column.encodings().map(|e| e.to_string()).collect(),
        compressed_bytes: column.compressed_size(),
        uncompressed_bytes: column.uncompressed_size(),
        min,
        max,
        nulls: column.statistics().and_then(|s| s.null_count_opt()),
    }
}

fn bounds(stats: &Statistics, timestamp: bool) -> (String, String) {
    match stats {
        Statistics::Int64(s) if timestamp => (opt(s.min_opt().map(|v| iso(*v))), opt(s.max_opt().map(|v| iso(*v)))),
        Statistics::Int64(s) => (opt(s.min_opt()), opt(s.max_opt())),
        Statistics::Int32(s) => (opt(s.min_opt()), opt(s.max_opt())),
        Statistics::Double(s) => (opt(s.min_opt()), opt(s.max_opt())),
        Statistics::ByteArray(s) => (
            opt(s.min_opt().and_then(|v| v.as_utf8().ok())),
            opt(s.max_opt().and_then(|v| v.as_utf8().ok())),
        ),
        _ => (String::new(), String::new()),
    }
}

fn iso(ms: i64) -> String {
    timestamp_ms_to_datetime(ms)
        .map(|dt| dt.format("%Y-%m-%dT%H:%M:%SZ").to_string())
        .unwrap_or_default()
}

fn opt<T: ToString>(value: Option<T>) -> String {
    value.map(|v| v.to_string()).unwrap_or_default()
}
