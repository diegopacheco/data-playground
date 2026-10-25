import pyarrow.parquet as pq
from pyiceberg.manifest import ManifestContent, ManifestEntryStatus
from pyiceberg.table.snapshots import Operation, ancestors_between_ids

from lake import COLUMNS


def snapshots_between(table, from_id, to_id):
    found = list(ancestors_between_ids(
        from_snapshot_id_exclusive=from_id,
        to_snapshot_id_inclusive=to_id,
        table_metadata=table.metadata,
    ))
    if from_id is not None and found[-1].parent_snapshot_id != from_id:
        raise RuntimeError(f"watermark snapshot {from_id} is not an ancestor of {to_id}, a full resync is required")
    return list(reversed(found))


def by_id(rows):
    return {row["id"]: row for row in rows.select(COLUMNS).to_pylist()}


def change(technique, operations, before, after, files_read):
    return {
        "technique": technique,
        "operations": operations,
        "inserted": [after[i] for i in sorted(after.keys() - before.keys())],
        "updated": [after[i] for i in sorted(after.keys() & before.keys()) if after[i] != before[i]],
        "deleted": sorted(before.keys() - after.keys()),
        "carried_over": sum(1 for i in after.keys() & before.keys() if after[i] == before[i]),
        "files_read": files_read,
        "rows_read": len(before) + len(after),
    }


def append_scan(table, from_id, to_id):
    scan = table.incremental_append_scan(from_snapshot_id_exclusive=from_id, to_snapshot_id_inclusive=to_id)
    return by_id(scan.to_arrow()), len(list(scan.plan_files()))


def changed_files(table, snapshots):
    added, removed = set(), set()
    for snapshot in snapshots:
        for manifest in snapshot.manifests(table.io):
            if manifest.added_snapshot_id != snapshot.snapshot_id:
                continue
            if manifest.content != ManifestContent.DATA:
                raise RuntimeError("delete files found: merge-on-read changes are not covered by the file changelog")
            for entry in manifest.fetch_manifest_entry(table.io, discard_deleted=False):
                if entry.snapshot_id != snapshot.snapshot_id:
                    continue
                path = entry.data_file.file_path
                if entry.status == ManifestEntryStatus.ADDED:
                    added.add(path)
                elif entry.status == ManifestEntryStatus.DELETED and path in added:
                    added.discard(path)
                elif entry.status == ManifestEntryStatus.DELETED:
                    removed.add(path)
    return added, removed


def read_files(table, paths):
    rows = {}
    for path in sorted(paths):
        with table.io.new_input(path).open() as f:
            rows.update(by_id(pq.read_table(f, columns=COLUMNS)))
    return rows


def between(table, from_id, to_id):
    if from_id == to_id:
        return change("none", [], {}, {}, 0)
    snapshots = snapshots_between(table, from_id, to_id)
    operations = [s.summary.operation.value for s in snapshots]
    if all(s.summary.operation == Operation.APPEND for s in snapshots):
        after, files = append_scan(table, from_id, to_id)
        return change("incremental_append_scan", operations, {}, after, files)
    added, removed = changed_files(table, snapshots)
    return change("file_changelog", operations, read_files(table, removed), read_files(table, added), len(added) + len(removed))


def full_compare(table, from_id, to_id):
    before = by_id(table.scan(snapshot_id=from_id).to_arrow()) if from_id is not None else {}
    after = by_id(table.scan(snapshot_id=to_id).to_arrow())
    return change("full_snapshot_compare", [], before, after, 0)
