from netflow_sentry.collector import metrics
from netflow_sentry.proto_gen import flow_pb2


def _record(protocol="tcp", status="ESTABLISHED"):
    return flow_pb2.FlowRecord(protocol=protocol, status=status)


def test_record_batch_increments_counters_per_record():
    agent_id = "metrics-test-agent"
    before = metrics.FLOWS_RECEIVED_TOTAL.labels(
        agent_id=agent_id, protocol="tcp", status="ESTABLISHED"
    )._value.get()

    metrics.record_batch(agent_id, [_record(), _record(), _record(status="LISTEN")])

    after_established = metrics.FLOWS_RECEIVED_TOTAL.labels(
        agent_id=agent_id, protocol="tcp", status="ESTABLISHED"
    )._value.get()
    after_listen = metrics.FLOWS_RECEIVED_TOTAL.labels(
        agent_id=agent_id, protocol="tcp", status="LISTEN"
    )._value.get()

    assert after_established == before + 2
    assert after_listen == 1

    assert metrics.LAST_BATCH_SIZE.labels(agent_id=agent_id)._value.get() == 3
    assert (
        metrics.BATCHES_RECEIVED_TOTAL.labels(agent_id=agent_id)._value.get() >= 1
    )
