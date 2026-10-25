import sys

import db
import lake
import sync
import verify

ROUNDS = [
    ("initial load", lake.append, "round1-initial.csv"),
    ("append", lake.append, "round2-append.csv"),
    ("update", lake.upsert, "round3-update.csv"),
    ("delete", lake.delete, "round4-delete.csv"),
    ("no-op", None, None),
]


def main():
    conn = db.connect()
    db.init_schema(conn)
    table = lake.create_table()
    for label, apply, name in ROUNDS:
        if apply:
            apply(table, lake.read_csv(name))
        r = sync.sync(conn, table, label)
        print(
            f"round {r['round']} {label}: technique={r['technique']} table_rows={r['table_rows']} "
            f"inserted={len(r['inserted'])} updated={len(r['updated'])} deleted={len(r['deleted'])} "
            f"rows_embedded={r['rows_embedded']} model_calls={r['model_calls']} vectors={r['vectors_after']}"
        )
    report = verify.run(conn, table)
    print(verify.summary(report))
    sys.exit(0 if report["equal"] else 1)


if __name__ == "__main__":
    main()
