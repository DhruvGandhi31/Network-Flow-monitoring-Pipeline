import gzip
import json
import re
from unittest.mock import MagicMock

import pytest

from netflow_sentry.collector import metrics
from netflow_sentry.collector.archive import (
    FlowArchiver,
    GCSSink,
    LocalDirSink,
    build_archiver,
    record_to_dict,
)
from netflow_sentry.common.config import CollectorConfig
from netflow_sentry.proto_gen import flow_pb2


class FakeSink:
    def __init__(self, fail_times=0):
        self.writes: list[tuple[str, bytes]] = []
        self.fail_times = fail_times

    def write(self, name, data):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("storage unavailable")
        self.writes.append((name, data))


def _record(**kw):
    defaults = {
        "agent_id": "a1",
        "src_ip": "10.0.0.1",
        "src_port": 5000,
        "dst_ip": "10.0.0.2",
        "dst_port": 443,
        "protocol": "tcp",
        "status": "ESTABLISHED",
        "process_name": "curl",
        "pid": 42,
        "timestamp_unix": 1_700_000_000,
    }
    defaults.update(kw)
    return flow_pb2.FlowRecord(**defaults)


def _rows(data: bytes) -> list[dict]:
    return [json.loads(line) for line in gzip.decompress(data).decode().splitlines()]


def _counter(c) -> float:
    return c._value.get()


def test_record_to_dict_covers_every_proto_field():
    # Guards against adding a field to flow.proto but forgetting to archive it.
    proto_fields = {f.name for f in flow_pb2.FlowRecord.DESCRIPTOR.fields}
    assert set(record_to_dict(_record(), 1.0)) == proto_fields | {"received_at"}


def test_record_to_dict_keeps_int64_as_number():
    row = record_to_dict(_record(timestamp_unix=1_700_000_000), 5.0)
    assert row["timestamp_unix"] == 1_700_000_000
    assert isinstance(row["timestamp_unix"], int)


def test_flush_writes_one_gzipped_ndjson_object_for_many_batches():
    sink = FakeSink()
    archiver = FlowArchiver(sink)
    archiver.add([_record(src_port=1), _record(src_port=2)])
    archiver.add([_record(src_port=3)])

    archiver.flush()

    assert len(sink.writes) == 1
    name, data = sink.writes[0]
    assert re.fullmatch(
        r"flows/dt=\d{4}-\d{2}-\d{2}/hour=\d{2}/\d{8}T\d{6}-[0-9a-f]{8}\.ndjson\.gz", name
    )
    assert [r["src_port"] for r in _rows(data)] == [1, 2, 3]


def test_flush_with_empty_buffer_writes_nothing():
    sink = FakeSink()
    FlowArchiver(sink).flush()
    assert sink.writes == []


def test_flush_updates_metrics():
    sink = FakeSink()
    archiver = FlowArchiver(sink)
    objects_before = _counter(metrics.ARCHIVE_OBJECTS_WRITTEN_TOTAL)
    records_before = _counter(metrics.ARCHIVE_RECORDS_WRITTEN_TOTAL)

    archiver.add([_record(), _record()])
    archiver.flush()

    assert _counter(metrics.ARCHIVE_OBJECTS_WRITTEN_TOTAL) == objects_before + 1
    assert _counter(metrics.ARCHIVE_RECORDS_WRITTEN_TOTAL) == records_before + 2


def test_failed_write_rebuffers_and_retries_without_losing_records():
    sink = FakeSink(fail_times=1)
    archiver = FlowArchiver(sink)
    failures_before = _counter(metrics.ARCHIVE_WRITE_FAILURES_TOTAL)

    archiver.add([_record(src_port=1)])
    archiver.flush()  # fails
    assert sink.writes == []
    assert _counter(metrics.ARCHIVE_WRITE_FAILURES_TOTAL) == failures_before + 1

    archiver.add([_record(src_port=2)])
    archiver.flush()  # succeeds; old record comes first
    assert [r["src_port"] for r in _rows(sink.writes[0][1])] == [1, 2]


def test_add_drops_records_beyond_cap_and_counts_them():
    sink = FakeSink()
    archiver = FlowArchiver(sink, max_buffered_records=2)
    dropped_before = _counter(metrics.ARCHIVE_RECORDS_DROPPED_TOTAL)

    archiver.add([_record(src_port=1), _record(src_port=2), _record(src_port=3)])
    archiver.flush()

    assert [r["src_port"] for r in _rows(sink.writes[0][1])] == [1, 2]
    assert _counter(metrics.ARCHIVE_RECORDS_DROPPED_TOTAL) == dropped_before + 1


def test_rebuffer_over_cap_drops_oldest():
    sink = FakeSink(fail_times=1)
    archiver = FlowArchiver(sink, max_buffered_records=2)

    archiver.add([_record(src_port=1), _record(src_port=2)])
    archiver.flush()  # fails, 2 rows re-buffered
    archiver.add([_record(src_port=3)])  # buffer already full -> dropped
    archiver.flush()

    assert [r["src_port"] for r in _rows(sink.writes[0][1])] == [1, 2]


def test_close_does_final_flush():
    sink = FakeSink()
    archiver = FlowArchiver(sink, flush_interval_seconds=3600)
    archiver.start()
    archiver.add([_record()])

    archiver.close()

    assert len(sink.writes) == 1


def test_background_thread_flushes_on_interval():
    sink = FakeSink()
    archiver = FlowArchiver(sink, flush_interval_seconds=0.05)
    archiver.start()
    archiver.add([_record()])
    try:
        for _ in range(100):
            if sink.writes:
                break
            archiver._stop.wait(0.05)
    finally:
        archiver.close()
    assert len(sink.writes) >= 1


def test_gcs_sink_uploads_gzip_blob():
    client = MagicMock()
    sink = GCSSink("my-bucket", client=client)

    sink.write("flows/x.ndjson.gz", b"data")

    client.bucket.assert_called_once_with("my-bucket")
    blob = client.bucket.return_value.blob
    blob.assert_called_once_with("flows/x.ndjson.gz")
    blob.return_value.upload_from_string.assert_called_once_with(
        b"data", content_type="application/gzip"
    )


def test_local_dir_sink_creates_nested_path(tmp_path):
    LocalDirSink(tmp_path).write("flows/dt=2026-01-01/hour=00/x.gz", b"abc")
    assert (tmp_path / "flows/dt=2026-01-01/hour=00/x.gz").read_bytes() == b"abc"


def _config(**kw):
    base = {
        "grpc_port": 1,
        "metrics_port": 2,
        "archive_bucket": "",
        "archive_local_dir": "",
        "archive_flush_seconds": 60,
        "archive_max_buffered_records": 10,
    }
    base.update(kw)
    return CollectorConfig(**base)


def test_build_archiver_disabled_by_default():
    assert build_archiver(_config()) is None


def test_build_archiver_rejects_both_backends():
    with pytest.raises(ValueError):
        build_archiver(_config(archive_bucket="b", archive_local_dir="/tmp/x"))


def test_build_archiver_local_dir(tmp_path):
    archiver = build_archiver(_config(archive_local_dir=str(tmp_path)))
    try:
        assert archiver is not None
        archiver.add([_record()])
    finally:
        archiver.close()
    assert len(list(tmp_path.rglob("*.ndjson.gz"))) == 1
