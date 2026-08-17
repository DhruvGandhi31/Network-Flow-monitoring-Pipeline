from unittest.mock import MagicMock, patch

from netflow_sentry.agent.capture import capture_flows


def _fake_conn(laddr, raddr, status, pid, conn_type=1):
    conn = MagicMock()
    conn.laddr = laddr
    conn.raddr = raddr
    conn.status = status
    conn.pid = pid
    conn.type = conn_type
    return conn


@patch("netflow_sentry.agent.capture.psutil.net_connections")
def test_capture_flows_builds_records_from_connections(mock_net_connections):
    mock_net_connections.return_value = [
        _fake_conn(("127.0.0.1", 5000), ("10.0.0.5", 443), "ESTABLISHED", pid=1234),
        _fake_conn(("0.0.0.0", 8080), None, "LISTEN", pid=None),
    ]

    with patch("netflow_sentry.agent.capture._process_name", return_value="python"):
        records = capture_flows(agent_id="test-agent")

    assert len(records) == 2

    established = records[0]
    assert established.src_ip == "127.0.0.1"
    assert established.src_port == 5000
    assert established.dst_ip == "10.0.0.5"
    assert established.dst_port == 443
    assert established.protocol == "tcp"
    assert established.status == "ESTABLISHED"
    assert established.pid == 1234
    assert established.agent_id == "test-agent"

    listening = records[1]
    assert listening.dst_ip == ""
    assert listening.dst_port == 0
    assert listening.pid == 0


@patch("netflow_sentry.agent.capture.psutil.net_connections")
def test_capture_flows_skips_connections_without_laddr(mock_net_connections):
    mock_net_connections.return_value = [_fake_conn(None, None, "NONE", pid=None)]

    records = capture_flows(agent_id="test-agent")

    assert records == []
