use std::error::Error;
use std::fs::{self, File};
use std::path::Path;

use arrow::array::{RecordBatch, TimestampMillisecondArray};
use arrow::compute::kernels::cmp::gt_eq;
use arrow::datatypes::SchemaRef;
use parquet::arrow::ArrowWriter;
use parquet::arrow::ProjectionMask;
use parquet::arrow::arrow_reader::{ArrowPredicateFn, ParquetRecordBatchReaderBuilder, RowFilter};
use parquet::basic::{Compression, ZstdLevel};
use parquet::file::metadata::ParquetMetaData;
use parquet::file::properties::{EnabledStatistics, WriterProperties};
use parquet::file::statistics::Statistics;
use parquet::schema::types::SchemaDescriptor;

pub const PROJECTED: [&str; 4] = ["category", "quantity", "price", "ts"];

pub struct Scan {
    pub batches: Vec<RecordBatch>,
    pub row_groups_total: usize,
    pub row_groups_read: Vec<usize>,
    pub rows_read: usize,
}

pub fn write(path: &Path, schema: SchemaRef, batches: &[RecordBatch], row_group_rows: usize) -> Result<u64, Box<dyn Error>> {
    if let Some(dir) = path.parent() {
        fs::create_dir_all(dir)?;
    }
    let props = WriterProperties::builder()
        .set_compression(Compression::ZSTD(ZstdLevel::try_new(3)?))
        .set_max_row_group_row_count(Some(row_group_rows))
        .set_statistics_enabled(EnabledStatistics::Chunk)
        .build();
    let staging = path.with_extension("parquet.tmp");
    let mut writer = ArrowWriter::try_new(File::create(&staging)?, schema, Some(props))?;
    for batch in batches {
        writer.write(batch)?;
    }
    writer.close()?;
    fs::rename(&staging, path)?;
    Ok(fs::metadata(path)?.len())
}

pub fn scan(path: &Path, from_ms: Option<i64>) -> Result<Scan, Box<dyn Error>> {
    let builder = ParquetRecordBatchReaderBuilder::try_new(File::open(path)?)?;
    let meta = builder.metadata().clone();
    let descr = builder.parquet_schema().clone();
    let ts = column_index(&descr, "ts")?;
    let projected = PROJECTED.iter().map(|name| column_index(&descr, name)).collect::<Result<Vec<_>, _>>()?;
    let row_groups_read = prune_row_groups(&meta, ts, from_ms);
    let mut builder = builder
        .with_projection(ProjectionMask::roots(&descr, projected))
        .with_row_groups(row_groups_read.clone());
    if let Some(from) = from_ms {
        let predicate = ArrowPredicateFn::new(ProjectionMask::roots(&descr, [ts]), move |batch: RecordBatch| {
            gt_eq(batch.column(0), &TimestampMillisecondArray::new_scalar(from))
        });
        builder = builder.with_row_filter(RowFilter::new(vec![Box::new(predicate)]));
    }
    let batches = builder.build()?.collect::<Result<Vec<_>, _>>()?;
    let rows_read = batches.iter().map(|b| b.num_rows()).sum();
    Ok(Scan { batches, row_groups_total: meta.num_row_groups(), row_groups_read, rows_read })
}

fn column_index(descr: &SchemaDescriptor, name: &str) -> Result<usize, String> {
    descr
        .columns()
        .iter()
        .position(|c| c.name() == name)
        .ok_or_else(|| format!("column {name} not found"))
}

fn prune_row_groups(meta: &ParquetMetaData, column: usize, from_ms: Option<i64>) -> Vec<usize> {
    (0..meta.num_row_groups())
        .filter(|&i| match (from_ms, meta.row_group(i).column(column).statistics()) {
            (Some(from), Some(Statistics::Int64(s))) => s.max_opt().is_none_or(|max| *max >= from),
            _ => true,
        })
        .collect()
}
