import json
from deltalake import write_deltalake
from lake import TABLE_URI, STORAGE, read_csv, open_table, revenue_by_category

INITIAL_ROWS = 150


def show(title, table):
    rows = revenue_by_category(table)
    total = round(sum(r["total_revenue"] for r in rows), 2)
    print(f"{title} version={table.version()} rows={sum(r['total_orders'] for r in rows)} revenue={total}")
    for r in rows:
        print(f"  {r['category']:<12} orders={r['total_orders']:<4} qty={r['total_quantity']:<4} revenue={r['total_revenue']:.2f}")


def write_initial(orders):
    write_deltalake(TABLE_URI, orders.slice(0, INITIAL_ROWS), mode="error", partition_by=["category"], storage_options=STORAGE)
    show("write", open_table())


def append_rest(orders):
    write_deltalake(TABLE_URI, orders.slice(INITIAL_ROWS), mode="append", storage_options=STORAGE)
    show("append", open_table())


def merge_updates(updates):
    metrics = (
        open_table()
        .merge(source=updates, predicate="t.order_id = s.order_id", source_alias="s", target_alias="t")
        .when_matched_update(updates={"price": "s.price"})
        .when_not_matched_insert_all()
        .execute()
    )
    print("merge", json.dumps({k: metrics[k] for k in ("num_target_rows_updated", "num_target_rows_inserted")}))
    show("merge", open_table())


def time_travel():
    show("time travel", open_table(0))


def history():
    for h in sorted(open_table().history(), key=lambda h: h["version"]):
        print(f"history version={h['version']} operation={h['operation']}")


def optimize():
    table = open_table()
    before = len(table.file_uris())
    metrics = table.optimize.compact()
    table = open_table()
    print(f"optimize files_before={before} files_after={len(table.file_uris())} added={metrics['numFilesAdded']} removed={metrics['numFilesRemoved']}")
    show("optimize", table)


def vacuum():
    table = open_table()
    candidates = table.vacuum(retention_hours=0, dry_run=True, enforce_retention_duration=False)
    deleted = table.vacuum(dry_run=False)
    print(f"vacuum candidates_at_0h={len(candidates)} deleted_at_default_retention={len(deleted)}")


def main():
    orders = read_csv("data/orders.csv")
    updates = read_csv("data/updates.csv")
    write_initial(orders)
    append_rest(orders)
    merge_updates(updates)
    time_travel()
    optimize()
    vacuum()
    history()


if __name__ == "__main__":
    main()
