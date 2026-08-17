"""Flow capture: snapshots active network connections via psutil.

This is a connection-table snapshot approach (portable, no admin/pcap
required) rather than raw packet capture. Each call returns one FlowRecord
per currently visible inet connection. A pcap-based capture (scapy) that
yields true byte/packet counters is a documented stretch goal in README.
"""

from __future__ import annotations

import time

import psutil

from netflow_sentry.proto_gen import flow_pb2


def _process_name(pid: int | None) -> str:
    if not pid:
        return ""
    try:
        return psutil.Process(pid).name()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return ""


def capture_flows(agent_id: str) -> list[flow_pb2.FlowRecord]:
    """Snapshot current inet connections and convert them to FlowRecords."""
    now = int(time.time())
    records: list[flow_pb2.FlowRecord] = []

    for conn in psutil.net_connections(kind="inet"):
        if not conn.laddr:
            continue

        laddr_ip, laddr_port = conn.laddr
        raddr_ip, raddr_port = conn.raddr if conn.raddr else ("", 0)
        protocol = "tcp" if conn.type == 1 else "udp"

        records.append(
            flow_pb2.FlowRecord(
                src_ip=laddr_ip,
                src_port=laddr_port,
                dst_ip=raddr_ip,
                dst_port=raddr_port,
                protocol=protocol,
                status=conn.status or "NONE",
                process_name=_process_name(conn.pid),
                pid=conn.pid or 0,
                timestamp_unix=now,
                agent_id=agent_id,
            )
        )

    return records
