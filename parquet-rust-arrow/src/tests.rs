use std::path::{Path, PathBuf};
use std::sync::Arc;

use arrow::array::{Float64Array, Int64Array, RecordBatch, StringArray};
use arrow::datatypes::{DataType, Field, Schema};

use crate::aggregate::{CategoryAgg, by_category};
use crate::{build_lake, day_start_ms, lake, metadata};

const EXPECTED_ALL: [(&str, usize, i64, f64); 6] = [
    ("electronics", 30, 54, 9618.24),
    ("sports", 34, 76, 6873.93),
    ("clothing", 35, 63, 3776.49),
    ("home", 32, 62, 3608.87),
    ("toys", 37, 74, 2451.82),
    ("books", 32, 64, 2008.27),
];

const EXPECTED_FROM_JAN_12: [(&str, usize, i64, f64); 6] = [
    ("electronics", 17, 34, 6225.98),
    ("sports", 15, 41, 3871.16),
    ("clothing", 22, 42, 2708.96),
    ("home", 20, 34, 1836.04),
    ("toys", 18, 38, 1055.75),
    ("books", 10, 22, 635.85),
];

struct TempLake(PathBuf);

impl Drop for TempLake {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.0);
    }
}

impl std::ops::Deref for TempLake {
    type Target = Path;
    fn deref(&self) -> &Path {
        &self.0
    }
}

fn lake_file(name: &str) -> TempLake {
    let path = std::env::temp_dir().join(format!("i12-parquet-rust-arrow-{}-{name}.parquet", std::process::id()));
    build_lake(Path::new("data/orders.csv"), &path).unwrap();
    TempLake(path)
}

fn assert_matches(actual: &[CategoryAgg], expected: &[(&str, usize, i64, f64)]) {
    let got: Vec<(&str, usize, i64, f64)> = actual
        .iter()
        .map(|a| (a.category.as_str(), a.orders, a.quantity, (a.revenue * 100.0).round() / 100.0))
        .collect();
    assert_eq!(got, expected);
}

#[test]
fn full_scan_revenue_per_category_matches_the_csv_totals() {
    let path = lake_file("full");
    let scan = lake::scan(&path, None).unwrap();
    assert_eq!(scan.rows_read, 200);
    assert_matches(&by_category(&scan.batches).unwrap(), &EXPECTED_ALL);
}

#[test]
fn every_order_lands_in_exactly_one_category() {
    let path = lake_file("totals");
    let aggs = by_category(&lake::scan(&path, None).unwrap().batches).unwrap();
    assert_eq!(aggs.iter().map(|a| a.orders).sum::<usize>(), 200);
    assert_eq!(aggs.iter().map(|a| a.quantity).sum::<i64>(), 393);
}

#[test]
fn date_filter_only_counts_orders_on_or_after_the_cutoff() {
    let path = lake_file("filtered");
    let scan = lake::scan(&path, Some(day_start_ms("2026-01-12").unwrap())).unwrap();
    assert_eq!(scan.rows_read, 102);
    assert_matches(&by_category(&scan.batches).unwrap(), &EXPECTED_FROM_JAN_12);
}

#[test]
fn row_group_stats_skip_groups_that_end_before_the_cutoff() {
    let path = lake_file("pruned");
    let early = lake::scan(&path, Some(day_start_ms("2026-01-12").unwrap())).unwrap();
    assert_eq!(early.row_groups_total, 4);
    assert_eq!(early.row_groups_read, vec![1, 2, 3]);
    let late = lake::scan(&path, Some(day_start_ms("2026-01-16").unwrap())).unwrap();
    assert_eq!(late.row_groups_read, vec![3]);
    assert_eq!(late.rows_read, 42);
}

#[test]
fn projection_reads_only_the_columns_the_aggregates_need() {
    let path = lake_file("projection");
    let scan = lake::scan(&path, None).unwrap();
    let names: Vec<String> = scan.batches[0].schema().fields().iter().map(|f| f.name().clone()).collect();
    assert_eq!(names, lake::PROJECTED);
}

#[test]
fn file_is_zstd_compressed_in_row_groups_of_fifty_with_stats() {
    let path = lake_file("metadata");
    let info = metadata::read(&path).unwrap();
    assert_eq!(info.num_rows, 200);
    assert_eq!(info.row_groups.iter().map(|rg| rg.rows).collect::<Vec<_>>(), vec![50, 50, 50, 50]);
    let ts = &info.row_groups[0].columns[6];
    assert_eq!(ts.name, "ts");
    assert_eq!(ts.compression, "ZSTD");
    assert_eq!(ts.min, "2026-01-05T10:05:00Z");
    assert!(info.row_groups.iter().all(|rg| rg.columns.iter().all(|c| c.compression == "ZSTD" && !c.max.is_empty())));
}

#[test]
fn price_stats_follow_the_csv_prices() {
    let path = lake_file("prices");
    let aggs = by_category(&lake::scan(&path, None).unwrap().batches).unwrap();
    let electronics = aggs.iter().find(|a| a.category == "electronics").unwrap();
    assert_eq!(electronics.min_price, 15.51);
    assert_eq!(electronics.max_price, 477.23);
    assert!((electronics.avg_price - 196.7067).abs() < 0.0001);
}

#[test]
fn revenue_is_quantity_times_price_not_price_alone() {
    let schema = Arc::new(Schema::new(vec![
        Field::new("category", DataType::Utf8, false),
        Field::new("quantity", DataType::Int64, false),
        Field::new("price", DataType::Float64, false),
    ]));
    let batch = RecordBatch::try_new(
        schema,
        vec![
            Arc::new(StringArray::from(vec!["a", "b", "a"])),
            Arc::new(Int64Array::from(vec![3, 1, 2])),
            Arc::new(Float64Array::from(vec![10.0, 5.0, 1.5])),
        ],
    )
    .unwrap();
    let aggs = by_category(&[batch]).unwrap();
    assert_eq!(aggs[0].category, "a");
    assert_eq!((aggs[0].orders, aggs[0].quantity, aggs[0].revenue), (2, 5, 33.0));
    assert_eq!((aggs[1].orders, aggs[1].quantity, aggs[1].revenue), (1, 1, 5.0));
}

#[test]
fn empty_input_yields_no_categories() {
    assert!(by_category(&[]).unwrap().is_empty());
}

#[test]
fn malformed_day_is_rejected() {
    assert!(day_start_ms("2026-1-12").is_err());
    assert_eq!(day_start_ms("2026-01-12").unwrap(), 1_768_176_000_000);
}
