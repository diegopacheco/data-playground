use std::fs::File;
use std::path::Path;
use std::sync::Arc;

use arrow::csv::ReaderBuilder;
use arrow::datatypes::{DataType, Field, Schema, SchemaRef, TimeUnit};
use arrow::error::ArrowError;
use arrow::record_batch::RecordBatch;

pub fn schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("order_id", DataType::Int64, false),
        Field::new("customer", DataType::Utf8, false),
        Field::new("product", DataType::Utf8, false),
        Field::new("category", DataType::Utf8, false),
        Field::new("quantity", DataType::Int64, false),
        Field::new("price", DataType::Float64, false),
        Field::new("ts", DataType::Timestamp(TimeUnit::Millisecond, None), false),
    ]))
}

pub fn read_csv(path: &Path, batch_size: usize) -> Result<Vec<RecordBatch>, ArrowError> {
    let file = File::open(path)?;
    ReaderBuilder::new(schema())
        .with_header(true)
        .with_batch_size(batch_size)
        .build(file)?
        .collect()
}
