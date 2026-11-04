import asyncio
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
import nats
from nats.errors import TimeoutError as NatsTimeout
from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy, DiscardPolicy, ReplayPolicy, RetentionPolicy
from nats.js.errors import APIError, KeyNotFoundError, KeyWrongLastSequenceError, NoKeysError, NotFoundError, ServiceUnavailableError
from data import decode, encode, orders

SERVERS = os.environ.get("NATS_URLS", "nats://localhost:27301").split(",")
MONITORS = os.environ.get("MONITOR_URLS", "http://localhost:27304").split(",")
REPLICAS = int(os.environ.get("REPLICAS", "3"))
JS_TIMEOUT = float(os.environ.get("JS_TIMEOUT", "20"))


async def connect():
    return await nats.connect(servers=SERVERS, connect_timeout=5, max_reconnect_attempts=10, reconnect_time_wait=0.5)


async def retry(call, seconds=60):
    deadline = time.monotonic() + seconds
    while True:
        try:
            return await call()
        except (NatsTimeout, ServiceUnavailableError):
            if time.monotonic() > deadline:
                raise
            await asyncio.sleep(0.5)


async def reset(js, **config):
    async def delete():
        try:
            await js.delete_stream(config["name"])
        except NotFoundError:
            pass
    await retry(delete)
    await retry(lambda: js.add_stream(num_replicas=REPLICAS, **config))


async def state(js, stream):
    info = await js.stream_info(stream)
    s = info.state
    return {"messages": s.messages, "first_seq": s.first_seq, "last_seq": s.last_seq, "consumers": s.consumer_count}


async def ids_in(js, stream, first, last):
    out = []
    for seq in range(first, last + 1):
        try:
            out.append(decode((await js.get_msg(stream, seq)).data)["id"])
        except NotFoundError:
            pass
    return out


async def settled(js, stream):
    started = time.monotonic()
    while True:
        s = await state(js, stream)
        left = await ids_in(js, stream, 1, s["last_seq"])
        if s["messages"] == len(left) or time.monotonic() - started > 3:
            s["left_ids"] = left
            s["settle_ms"] = round((time.monotonic() - started) * 1000)
            return s
        await asyncio.sleep(0.1)


async def fetch_some(sub, batch, timeout):
    async def fetch():
        try:
            return await sub.fetch(batch, timeout=timeout)
        except NatsTimeout:
            return []
    return await retry(fetch, 20)


async def drain(sub, timeout=1.0, ack=True, batch=100):
    out = []
    while True:
        msgs = await fetch_some(sub, batch, timeout)
        if not msgs:
            return out
        for m in msgs:
            out.append({"id": decode(m.data)["id"], "seq": m.metadata.sequence.stream, "subject": m.subject, "delivered": m.metadata.num_delivered, "at": time.monotonic()})
            if ack:
                await m.ack_sync()


async def retention():
    nc = await connect()
    js = nc.jetstream(timeout=JS_TIMEOUT)
    try:
        data = orders(80)
        await reset(js, name="RET_LIMITS", subjects=["limits.orders"], retention=RetentionPolicy.LIMITS, max_msgs=50, discard=DiscardPolicy.OLD)
        for o in data:
            await js.publish("limits.orders", encode(o))
        limits = await state(js, "RET_LIMITS")
        limits["published"] = len(data)
        limits["max_msgs"] = 50
        limits["kept_ids"] = await ids_in(js, "RET_LIMITS", limits["first_seq"], limits["last_seq"])

        jobs = orders(20)
        await reset(js, name="RET_WORK", subjects=["work.jobs"], retention=RetentionPolicy.WORK_QUEUE)
        for o in jobs:
            await js.publish("work.jobs", encode(o))
        workers = await js.pull_subscribe("work.jobs", durable="workers", stream="RET_WORK")
        done = []
        for m in await fetch_some(workers, 12, 5):
            await m.ack_sync()
            done.append(decode(m.data)["id"])
        work = await settled(js, "RET_WORK")
        work["published"] = len(jobs)
        work["acked_ids"] = done
        try:
            await js.add_consumer("RET_WORK", ConsumerConfig(durable_name="second", ack_policy=AckPolicy.EXPLICIT))
            work["second_consumer"] = "accepted"
        except APIError as e:
            work["second_consumer"] = f"rejected: {e.description}"

        events = orders(10)
        await reset(js, name="RET_INTEREST", subjects=["interest.orders"], retention=RetentionPolicy.INTEREST)
        email = await js.pull_subscribe("interest.orders", durable="email", stream="RET_INTEREST")
        audit = await js.pull_subscribe("interest.orders", durable="audit", stream="RET_INTEREST")
        for o in events:
            await js.publish("interest.orders", encode(o))
        for m in await fetch_some(email, 10, 5):
            await m.ack_sync()
        audit_acked = []
        for m in await fetch_some(audit, 4, 5):
            await m.ack_sync()
            audit_acked.append(decode(m.data)["id"])
        interest = await settled(js, "RET_INTEREST")
        interest["published"] = len(events)
        interest["email_acked"] = 10
        interest["audit_acked_ids"] = audit_acked
        return {"limits": limits, "workqueue": work, "interest": interest}
    finally:
        await nc.close()


async def consumers():
    nc = await connect()
    js = nc.jetstream(timeout=JS_TIMEOUT)
    try:
        data = orders(10)
        await reset(js, name="ORDERS", subjects=["orders.>"])
        for o in data:
            await js.publish(f"orders.{o['region']}", encode(o))
        cfg = ConsumerConfig(ack_wait=2, max_deliver=3, ack_policy=AckPolicy.EXPLICIT)
        billing = await js.pull_subscribe("orders.>", durable="billing", stream="ORDERS", config=cfg)
        plan = {8: "nak", 9: "no ack", 10: "term"}
        log = []
        start = time.monotonic()
        for m in await fetch_some(billing, 10, 5):
            oid = decode(m.data)["id"]
            action = plan.get(oid, "ack")
            if action == "ack":
                await m.ack_sync()
            elif action == "nak":
                await m.nak()
            elif action == "term":
                await m.term()
            log.append({"id": oid, "seq": m.metadata.sequence.stream, "delivered": m.metadata.num_delivered, "action": action, "ms": round((time.monotonic() - start) * 1000)})
        redelivered = []
        deadline = time.monotonic() + 8
        while len(redelivered) < 2 and time.monotonic() < deadline:
            for m in await fetch_some(billing, 10, 1):
                await m.ack_sync()
                oid = decode(m.data)["id"]
                redelivered.append(oid)
                log.append({"id": oid, "seq": m.metadata.sequence.stream, "delivered": m.metadata.num_delivered, "action": "ack (redelivery)", "ms": round((time.monotonic() - start) * 1000)})
        await nc.close()

        nc = await connect()
        js = nc.jetstream(timeout=JS_TIMEOUT)
        more = orders(2, start=11)
        for o in more:
            await js.publish(f"orders.{o['region']}", encode(o))
        again = await js.pull_subscribe("orders.>", durable="billing", stream="ORDERS")
        resumed = [r["id"] for r in await drain(again)]
        info = await js.consumer_info("ORDERS", "billing")

        await js.publish("orders.poison", encode({"id": 99, "region": "poison", "cents": 0}))
        poison = await js.pull_subscribe("orders.poison", durable="poison", stream="ORDERS", config=ConsumerConfig(max_deliver=3, ack_wait=1, ack_policy=AckPolicy.EXPLICIT))
        attempts = []
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            for m in await fetch_some(poison, 1, 0.5):
                attempts.append(m.metadata.num_delivered)
                await m.nak()
        pinfo = await js.consumer_info("ORDERS", "poison")
        return {
            "published": len(data) + len(more),
            "plan": {str(k): v for k, v in plan.items()},
            "log": log,
            "redelivered_ids": redelivered,
            "resumed_ids": resumed,
            "billing": {"num_pending": info.num_pending, "num_ack_pending": info.num_ack_pending, "num_redelivered": info.num_redelivered, "delivered_stream_seq": info.delivered.stream_seq, "ack_floor_stream_seq": info.ack_floor.stream_seq},
            "poison": {"max_deliver": 3, "attempts": attempts, "num_ack_pending": pinfo.num_ack_pending},
        }
    finally:
        if not nc.is_closed:
            await nc.close()


def now_utc():
    return datetime.now(timezone.utc)


async def replay():
    nc = await connect()
    js = nc.jetstream(timeout=JS_TIMEOUT)
    try:
        data = orders(30)
        await reset(js, name="EVENTS", subjects=["events.>"])
        marks = []
        for b in range(3):
            if b:
                await asyncio.sleep(0.7)
            marks.append(now_utc())
            await asyncio.sleep(0.7)
            for o in data[b * 10:(b + 1) * 10]:
                await js.publish(f"events.{o['region']}", encode(o))

        async def read(cfg, timeout=1.0, batch=100):
            cfg.ack_policy = AckPolicy.EXPLICIT
            cfg.inactive_threshold = 10
            sub = await js.pull_subscribe("events.>", stream="EVENTS", config=cfg)
            rows = await drain(sub, timeout, batch=batch)
            await sub.unsubscribe()
            return rows

        by_seq = await read(ConsumerConfig(deliver_policy=DeliverPolicy.BY_START_SEQUENCE, opt_start_seq=21))
        by_time = await read(ConsumerConfig(deliver_policy=DeliverPolicy.BY_START_TIME, opt_start_time=marks[1]))
        last = await read(ConsumerConfig(deliver_policy=DeliverPolicy.LAST_PER_SUBJECT))
        everything = await read(ConsumerConfig(deliver_policy=DeliverPolicy.ALL))
        started = time.monotonic()
        original = await read(ConsumerConfig(deliver_policy=DeliverPolicy.BY_START_SEQUENCE, opt_start_seq=10, replay_policy=ReplayPolicy.ORIGINAL), timeout=3, batch=1)
        gap_ms = round((original[1]["at"] - original[0]["at"]) * 1000) if len(original) > 1 else None
        msg = await js.get_msg("EVENTS", 15)
        return {
            "published": len(data),
            "batch_start_times": [m.isoformat() for m in marks],
            "from_seq_21": [r["id"] for r in by_seq],
            "from_time_batch2": [r["id"] for r in by_time],
            "from_time_value": marks[1].isoformat(),
            "last_per_subject": {r["subject"]: r["id"] for r in last},
            "all": [r["id"] for r in everything],
            "original_pace": {"ids": [r["id"] for r in original], "gap_between_seq10_and_seq11_ms": gap_ms, "instant_gap_ms": round((everything[10]["at"] - everything[9]["at"]) * 1000), "total_ms": round((original[-1]["at"] - started) * 1000) if original else None},
            "get_msg_seq_15": {"subject": msg.subject, "id": decode(msg.data)["id"]},
        }
    finally:
        await nc.close()


async def keys(bucket):
    for _ in range(10):
        try:
            return await bucket.keys()
        except NoKeysError:
            await asyncio.sleep(0.3)
    return []


async def kv():
    nc = await connect()
    js = nc.jetstream(timeout=JS_TIMEOUT)
    try:
        async def drop():
            try:
                await js.delete_key_value("CONFIG")
            except NotFoundError:
                pass
        await retry(drop)
        bucket = await retry(lambda: js.create_key_value(bucket="CONFIG", history=5, replicas=REPLICAS))
        watched = []
        watcher = await bucket.watch("feature.*", include_history=False)

        async def collect():
            async for e in watcher:
                if e is None:
                    continue
                watched.append({"key": e.key, "revision": e.revision, "op": e.operation or "PUT", "value": e.value.decode() if e.value else None})

        task = asyncio.create_task(collect())
        for v in range(1, 8):
            await bucket.put("feature.checkout", f"v{v}".encode())
        current = await bucket.get("feature.checkout")
        history = [{"revision": e.revision, "value": e.value.decode()} for e in await bucket.history("feature.checkout")]
        try:
            await bucket.update("feature.checkout", b"stale", last=current.revision - 1)
            stale = "accepted"
        except KeyWrongLastSequenceError as e:
            stale = f"rejected: {e.description}"
        cas_rev = await bucket.update("feature.checkout", b"v8", last=current.revision)
        created = await bucket.create("feature.search", b"on")
        try:
            await bucket.create("feature.search", b"again")
            duplicate = "accepted"
        except Exception as e:
            duplicate = f"rejected: {type(e).__name__}"
        await bucket.delete("feature.search")
        try:
            await bucket.get("feature.search")
            deleted = "still readable"
        except KeyNotFoundError as e:
            deleted = f"{type(e).__name__} op={e.op}"
        await asyncio.sleep(0.5)
        await watcher.stop()
        task.cancel()
        status = await bucket.status()
        info = await js.stream_info("KV_CONFIG")
        return {
            "bucket": "CONFIG",
            "history_limit": 5,
            "puts": [f"v{v}" for v in range(1, 8)],
            "current": {"revision": current.revision, "value": current.value.decode()},
            "history": history,
            "stale_update": stale,
            "cas_update_revision": cas_rev,
            "create_revision": created,
            "duplicate_create": duplicate,
            "after_delete": deleted,
            "keys": await keys(bucket),
            "watched": watched,
            "backing_stream": {"name": "KV_CONFIG", "messages": info.state.messages, "replicas": info.config.num_replicas, "values": status.values},
        }
    finally:
        await nc.close()


def monitor(url, path):
    with urllib.request.urlopen(f"{url}{path}", timeout=3) as r:
        return json.load(r)


def node(url):
    try:
        varz = monitor(url, "/varz")
        jsz = monitor(url, "/jsz?accounts=true&streams=true")
        streams = {}
        for acc in jsz.get("account_details") or []:
            for s in acc.get("stream_detail") or []:
                streams[s["name"]] = {"messages": s["state"]["messages"], "last_seq": s["state"]["last_seq"], "leader": (s.get("cluster") or {}).get("leader")}
        return {"url": url, "up": True, "name": varz["server_name"], "version": varz["version"], "mem_mb": round(varz["mem"] / 1048576, 1), "routes": varz.get("routes", 0), "meta_leader": (jsz.get("meta_cluster") or {}).get("leader"), "streams": streams}
    except Exception as e:
        return {"url": url, "up": False, "error": str(e)}


async def ensure_ledger(js):
    try:
        await js.stream_info("LEDGER")
    except NotFoundError:
        await js.add_stream(name="LEDGER", subjects=["ledger.>"], num_replicas=REPLICAS)


async def placement(js, name):
    info = await js.stream_info(name)
    c = info.cluster
    return {"stream": name, "leader": c.leader if c else None, "replicas": [{"name": r.name, "current": r.current, "lag": r.lag or 0} for r in (c.replicas or [])] if c else [], "messages": info.state.messages, "last_seq": info.state.last_seq}


async def cluster():
    nc = await connect()
    js = nc.jetstream(timeout=JS_TIMEOUT)
    try:
        await ensure_ledger(js)
        streams = []
        for name in ["LEDGER", "ORDERS", "EVENTS", "KV_CONFIG", "RET_LIMITS", "RET_WORK", "RET_INTEREST"]:
            try:
                streams.append(await placement(js, name))
            except NotFoundError:
                pass
        return {"connected_to": nc.connected_url.netloc if nc.connected_url else None, "nodes": [node(u) for u in MONITORS], "streams": streams}
    finally:
        await nc.close()


async def ledger(count):
    nc = await connect()
    js = nc.jetstream(timeout=JS_TIMEOUT)
    try:
        await ensure_ledger(js)
        before = (await js.stream_info("LEDGER")).state.last_seq
        acked = 0
        for i in range(count):
            ack = await js.publish("ledger.entries", encode({"id": before + i + 1, "region": "ledger", "cents": i}), timeout=5)
            acked += 1 if ack.seq else 0
        after = await placement(js, "LEDGER")
        return {"requested": count, "acked": acked, "last_seq_before": before, "last_seq_after": after["last_seq"], "placement": after}
    finally:
        await nc.close()


async def stepdown():
    nc = await connect()
    js = nc.jetstream(timeout=JS_TIMEOUT)
    try:
        await ensure_ledger(js)
        old = (await placement(js, "LEDGER"))["leader"]
        await nc.request("$JS.API.STREAM.LEADER.STEPDOWN.LEDGER", b"", timeout=5)
        new = old
        deadline = time.monotonic() + 10
        while (new == old or new is None) and time.monotonic() < deadline:
            await asyncio.sleep(0.3)
            new = (await placement(js, "LEDGER"))["leader"]
        ack = await js.publish("ledger.entries", encode({"id": 0, "region": "ledger", "cents": 0}), timeout=5)
        return {"old_leader": old, "new_leader": new, "publish_after_stepdown_seq": ack.seq}
    finally:
        await nc.close()


SCENARIOS = {"retention": retention, "consumers": consumers, "replay": replay, "kv": kv}
