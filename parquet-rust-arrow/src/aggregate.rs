use std::collections::BTreeSet;

use arrow::array::{Array, AsArray, RecordBatch, StringArray};
use arrow::compute::kernels::cmp::eq;
use arrow::compute::kernels::numeric::mul;
use arrow::compute::{cast, concat_batches, filter, max, min, sum};
use arrow::datatypes::{DataType, Float64Type, Int64Type};
use arrow::error::ArrowError;

#[derive(Debug, Clone, PartialEq)]
pub struct CategoryAgg {
    pub category: String,
    pub orders: usize,
    pub quantity: i64,
    pub revenue: f64,
    pub avg_price: f64,
    pub min_price: f64,
    pub max_price: f64,
}

pub fn by_category(batches: &[RecordBatch]) -> Result<Vec<CategoryAgg>, ArrowError> {
    let Some(first) = batches.first() else {
        return Ok(Vec::new());
    };
    let batch = concat_batches(&first.schema(), batches)?;
    let categories = column(&batch, "category")?.as_string::<i32>().clone();
    let quantity = column(&batch, "quantity")?.as_primitive::<Int64Type>().clone();
    let price = column(&batch, "price")?.as_primitive::<Float64Type>().clone();
    let revenue = mul(&cast(&quantity, &DataType::Float64)?, &price)?;
    let revenue = revenue.as_primitive::<Float64Type>();
    let names: BTreeSet<&str> = categories.iter().flatten().collect();
    let mut result = names
        .into_iter()
        .map(|name| {
            let mask = eq(&categories, &StringArray::new_scalar(name))?;
            let q = filter(&quantity, &mask)?;
            let p = filter(&price, &mask)?;
            let r = filter(revenue, &mask)?;
            let p = p.as_primitive::<Float64Type>();
            let orders = mask.true_count();
            Ok(CategoryAgg {
                category: name.to_string(),
                orders,
                quantity: sum(q.as_primitive::<Int64Type>()).unwrap_or(0),
                revenue: sum(r.as_primitive::<Float64Type>()).unwrap_or(0.0),
                avg_price: sum(p).unwrap_or(0.0) / orders as f64,
                min_price: min(p).unwrap_or(0.0),
                max_price: max(p).unwrap_or(0.0),
            })
        })
        .collect::<Result<Vec<_>, ArrowError>>()?;
    result.sort_by(|a, b| b.revenue.total_cmp(&a.revenue));
    Ok(result)
}

fn column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a dyn Array, ArrowError> {
    batch
        .column_by_name(name)
        .map(|c| c.as_ref())
        .ok_or_else(|| ArrowError::SchemaError(format!("column {name} not found")))
}
