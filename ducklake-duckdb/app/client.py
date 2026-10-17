import os
from lake import connect, commit, ORDERS_CSV


def count(con):
    return con.execute("SELECT count(*) FROM lake.orders").fetchone()[0]


def main():
    con = connect()
    before = count(con)
    commit(con, "client B loads remaining 50 orders", f"INSERT INTO lake.orders SELECT * FROM {ORDERS_CSV} OFFSET 150")
    print(f"client B pid={os.getpid()} saw rows={before} and committed rows={count(con)}")


if __name__ == "__main__":
    main()
