import json

LIFECYCLE = ["OrderPlaced", "OrderPaid", "OrderShipped", "OrderDelivered"]


def emit(con, aggregatetype, aggregateid, kind, payload):
    con.execute(
        "INSERT INTO outbox (aggregatetype, aggregateid, type, payload) VALUES (%s, %s, %s, %s)",
        (aggregatetype, aggregateid, kind, json.dumps(payload)),
    )


def register_customer(con, customer_id, name, tier):
    con.execute("INSERT INTO customers VALUES (%s, %s, %s)", (customer_id, name, tier))
    emit(con, "customer", customer_id, "CustomerRegistered", {"customer_id": customer_id, "name": name, "tier": tier})


def place_order(con, order_id, customer_id, amount):
    emit(con, "order", order_id, LIFECYCLE[0], {"order_id": order_id, "customer_id": customer_id, "amount": amount, "version": 1})
    con.execute("INSERT INTO orders VALUES (%s, %s, %s, 'PLACED', 1)", (order_id, customer_id, amount))


def advance_order(con, order_id):
    version = con.execute("UPDATE orders SET version = version + 1 WHERE order_id = %s RETURNING version", (order_id,)).fetchone()[0]
    kind = LIFECYCLE[version - 1]
    con.execute("UPDATE orders SET status = %s WHERE order_id = %s", (kind[5:].upper(), order_id))
    emit(con, "order", order_id, kind, {"order_id": order_id, "version": version})
