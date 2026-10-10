pub mod aggregate;
pub mod json;
pub mod lake;
pub mod metadata;
pub mod orders;
#[cfg(test)]
mod tests;

use std::error::Error;
use std::path::Path;

use arrow::compute::kernels::cast_utils::string_to_timestamp_nanos;

pub const CSV_BATCH_ROWS: usize = 64;
pub const ROW_GROUP_ROWS: usize = 50;

pub fn build_lake(csv: &Path, parquet: &Path) -> Result<u64, Box<dyn Error>> {
    let batches = orders::read_csv(csv, CSV_BATCH_ROWS)?;
    lake::write(parquet, orders::schema(), &batches, ROW_GROUP_ROWS)
}

pub fn day_start_ms(day: &str) -> Result<i64, String> {
    let valid = day.len() == 10 && day.chars().enumerate().all(|(i, c)| if i == 4 || i == 7 { c == '-' } else { c.is_ascii_digit() });
    if !valid {
        return Err(format!("invalid day {day}, expected YYYY-MM-DD"));
    }
    string_to_timestamp_nanos(&format!("{day}T00:00:00Z"))
        .map(|ns| ns / 1_000_000)
        .map_err(|e| e.to_string())
}
