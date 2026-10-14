from unittest.mock import MagicMock

from netflow_sentry.collector.server import FlowCollectorServicer
from netflow_sentry.proto_gen import flow_pb2


def _batch(agent_id, n):
    return flow_pb2.FlowBatch(
        agent_id=agent_id,
        records=[flow_pb2.FlowRecord(agent_id=agent_id, protocol="tcp") for _ in range(n)],
    )


def _context():
    ctx = MagicMock()
    ctx.peer.return_value = "ipv4:127.0.0.1:1234"
    return ctx


def test_stream_flows_acks_every_batch():
    servicer = FlowCollectorServicer()

    acks = list(servicer.StreamFlows(iter([_batch("srv-test", 2), _batch("srv-test", 0)]), _context()))

    assert [a.records_received for a in acks] == [2, 0]
    assert all(a.success for a in acks)
    assert acks[1].message == "ok:batch#2"


def test_stream_flows_hands_records_to_archiver():
    archiver = MagicMock()
    servicer = FlowCollectorServicer(archiver)

    list(servicer.StreamFlows(iter([_batch("srv-test", 3)]), _context()))

    archiver.add.assert_called_once()
    assert len(archiver.add.call_args.args[0]) == 3


def test_stream_flows_works_without_archiver():
    servicer = FlowCollectorServicer(archiver=None)
    assert len(list(servicer.StreamFlows(iter([_batch("srv-test", 1)]), _context()))) == 1
