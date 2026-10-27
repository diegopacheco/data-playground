import sys
from lake import connect


def main():
    con = connect()
    interactive = len(sys.argv) == 1 and sys.stdin.isatty()
    if interactive:
        print("tables: lake.redpanda.orders_kv, lake.redpanda.orders_typed (one statement per line, ctrl-d to quit)")
    for sql in sys.argv[1:] or sys.stdin:
        if sql.strip():
            try:
                result = con.sql(sql)
                if result is not None:
                    result.show(max_width=200)
            except Exception as e:
                print(f"ERROR: {e}", file=sys.stderr)
                if not interactive:
                    sys.exit(1)


if __name__ == "__main__":
    main()
