import sys
from vault import connect


def run(con, sql):
    for row in con.execute(sql).fetchall():
        print("|".join(str(v) for v in row))


if __name__ == "__main__":
    con = connect()
    if len(sys.argv) > 1:
        run(con, sys.argv[1])
    else:
        print("schemas: staging, raw_vault, business_vault, mart, audit. ctrl-d to quit")
        while True:
            try:
                sql = input("vault> ").strip()
            except EOFError:
                break
            if not sql:
                continue
            try:
                run(con, sql)
            except Exception as e:
                print(f"ERROR: {e}", file=sys.stderr)
