import json
import sys

import numpy as np

import db
import diff
import embed
import lake

TOLERANCE = 1e-3
MIN_COSINE = 0.9999


def reembed(conn, table):
    rows = sorted(table.scan().to_arrow().to_pylist(), key=lambda row: row["id"])
    fresh = dict(zip([row["id"] for row in rows], embed.embed_passages([row["text"] for row in rows])))
    stored = {r["id"]: r for r in db.rows(conn, "SELECT id, category, text, snapshot_id::text AS snapshot_id, embedding::text AS embedding FROM documents")}
    documents = []
    for row in rows:
        hit = stored.get(row["id"])
        if hit is None:
            continue
        vector = np.array(json.loads(hit["embedding"]), dtype=np.float32)
        documents.append({
            "id": row["id"],
            "category": row["category"],
            "text": row["text"],
            "snapshot_id": hit["snapshot_id"],
            "same_text": hit["text"] == row["text"],
            "max_abs_diff": float(np.abs(vector - fresh[row["id"]]).max()),
            "cosine": float(np.dot(vector, fresh[row["id"]]) / (np.linalg.norm(vector) * np.linalg.norm(fresh[row["id"]]))),
        })
    result = {
        "table_rows": len(rows),
        "store_rows": len(stored),
        "missing_ids": sorted(fresh.keys() - stored.keys()),
        "extra_ids": sorted(stored.keys() - fresh.keys()),
        "stale_text_ids": [d["id"] for d in documents if not d["same_text"]],
        "max_abs_diff": max((d["max_abs_diff"] for d in documents), default=0.0),
        "min_cosine": min((d["cosine"] for d in documents), default=0.0),
        "tolerance": TOLERANCE,
        "documents": documents,
    }
    result["equal"] = (
        not result["missing_ids"] and not result["extra_ids"] and not result["stale_text_ids"]
        and result["table_rows"] > 0 and result["max_abs_diff"] <= TOLERANCE and result["min_cosine"] >= MIN_COSINE
    )
    return result


def ids(change):
    return {
        "inserted": [row["id"] for row in change["inserted"]],
        "updated": [row["id"] for row in change["updated"]],
        "deleted": change["deleted"],
    }


def rounds(conn, table):
    result = []
    for r in db.rounds(conn):
        last = int(r["from_snapshot"]) if r["from_snapshot"] else None
        current = int(r["to_snapshot"])
        full = diff.full_compare(table, last, current)
        append_only = diff.append_scan(table, last, current)[0] if last != current else {}
        recorded = {key: r[key] for key in ("inserted", "updated", "deleted")}
        result.append({
            "round": r["round"],
            "label": r["label"],
            "technique": r["technique"],
            "changelog": {key: len(value) for key, value in recorded.items()},
            "full_compare": {key: len(value) for key, value in ids(full).items()},
            "rows_read_changelog": r["rows_read"],
            "rows_read_full_compare": full["rows_read"],
            "append_scan_rows": len(append_only),
            "equal": recorded == ids(full),
        })
    return result


def run(conn, table):
    report = reembed(conn, table)
    report["rounds"] = rounds(conn, table)
    report["watermark"] = str(db.watermark(conn))
    report["current_snapshot"] = str(table.current_snapshot().snapshot_id)
    report["equal"] = report["equal"] and all(r["equal"] for r in report["rounds"]) and report["watermark"] == report["current_snapshot"]
    return report


def summary(report):
    lines = [
        f"table_rows={report['table_rows']} store_rows={report['store_rows']} missing={len(report['missing_ids'])} "
        f"extra={len(report['extra_ids'])} stale_text={len(report['stale_text_ids'])}",
        f"max_abs_diff={report['max_abs_diff']:.2e} min_cosine={report['min_cosine']:.8f} tolerance={report['tolerance']:.0e}",
    ]
    for r in report["rounds"]:
        lines.append(
            f"round {r['round']} {r['label']}: changelog={r['changelog']} full_compare={r['full_compare']} "
            f"rows_read changelog={r['rows_read_changelog']} full_compare={r['rows_read_full_compare']} "
            f"append_scan_only_rows={r['append_scan_rows']} equal={r['equal']}"
        )
    lines.append(f"watermark={report['watermark']} current_snapshot={report['current_snapshot']} equal={report['equal']}")
    return "\n".join(lines)


if __name__ == "__main__":
    report = run(db.connect(), lake.load_table())
    print(summary(report))
    sys.exit(0 if report["equal"] else 1)
