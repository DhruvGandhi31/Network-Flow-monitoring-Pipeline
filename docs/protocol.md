# Protocol — `proto/flow.proto`

This file is the single source of truth for the wire format between agent
and collector. Nothing in `src/` should be treated as authoritative over it —
if the two disagree, the `.proto` is right and the generated code is stale.

## Messages

### `FlowRecord`

One observed connection at the moment of capture.

| Field | Type | Meaning |
|---|---|---|
| `src_ip` | string | Local address of the connection |
| `src_port` | uint32 | Local port |
| `dst_ip` | string | Remote address (empty for listening sockets with no peer) |
| `dst_port` | uint32 | Remote port (0 if no peer) |
| `protocol` | string | `"tcp"` or `"udp"` |
| `status` | string | Connection state as reported by the OS: `ESTABLISHED`, `LISTEN`, `TIME_WAIT`, `NONE` (UDP has no handshake state), etc. |
| `process_name` | string | Owning process name, resolved via `psutil.Process(pid).name()`; empty if unresolvable (`AccessDenied`/`NoSuchProcess`) or no pid |
| `pid` | int32 | Owning process id, 0 if unknown |
| `timestamp_unix` | int64 | Capture time, seconds since epoch |
| `agent_id` | string | Which agent produced this record |

### `FlowBatch`

What actually goes over the wire per send — a batch, not individual records,
to avoid one RPC message per connection.

| Field | Type | Meaning |
|---|---|---|
| `agent_id` | string | Redundant with each record's `agent_id`, but convenient at the batch level (used directly by `record_batch()` for labeling) |
| `batch_timestamp` | int64 | When this batch was assembled |
| `records` | repeated `FlowRecord` | Everything captured in this interval |

### `BatchAck`

Sent back by the collector for every `FlowBatch` received.

| Field | Type | Meaning |
|---|---|---|
| `success` | bool | Always `true` in the current implementation — there's no rejection path yet |
| `records_received` | int32 | Echoes `len(batch.records)`, lets the agent log confirmation |
| `message` | string | Free-form, currently `"ok:batch#N"` where N is a per-stream counter |

## Service

```proto
service FlowCollector {
  rpc StreamFlows(stream FlowBatch) returns (stream BatchAck);
}
```

A single bidirectional-streaming RPC. One call = one agent's entire session.
See `architecture.md` for why this shape was chosen over unary calls.

## Codegen

Stubs are **not** committed (see `.gitignore` —
`src/netflow_sentry/proto_gen/*_pb2*.py` and `*.pyi` are excluded; only
`__init__.py` is checked in). Regenerate with:

```bash
python scripts/generate_proto.py
```

This runs `grpc_tools.protoc` with `--python_out`, `--grpc_python_out`, and
`--pyi_out` all pointed at `src/netflow_sentry/proto_gen/`, producing
`flow_pb2.py`, `flow_pb2_grpc.py`, `flow_pb2.pyi`.

**Post-processing step**: `protoc`'s generated `flow_pb2_grpc.py` contains a
bare `import flow_pb2 as flow__pb2`, which only resolves if `proto_gen/` is
directly on `sys.path` — it breaks as soon as the file lives inside a
package (`netflow_sentry.proto_gen`). `generate_proto.py` rewrites that one
line after `protoc` runs, to `from . import flow_pb2 as flow__pb2`, making it
a valid relative import. This is the one hand-maintained piece of an
otherwise fully generated file — if you ever regenerate by calling `protoc`
directly instead of through the script, you'll hit an `ImportError` and need
to reapply this patch manually.

Both Dockerfiles (`docker/agent.Dockerfile`, `docker/collector.Dockerfile`)
run `python scripts/generate_proto.py` during the image build, so built
images always carry stubs matching the `.proto` they were built from — there
is no scenario where a committed, possibly-stale generated file ships in an
image.
