from cases import ADMIN, BOOTSTRAP
from trino import query

if __name__ == "__main__":
    for statement in BOOTSTRAP:
        query(statement, ADMIN)
    print(f"ran {len(BOOTSTRAP)} statements as {ADMIN}")
