"""Regenerate gRPC/protobuf Python stubs from proto/flow.proto.

Run with: python scripts/generate_proto.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROTO_DIR = ROOT / "proto"
OUT_DIR = ROOT / "src" / "netflow_sentry" / "proto_gen"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"-I{PROTO_DIR}",
        f"--python_out={OUT_DIR}",
        f"--grpc_python_out={OUT_DIR}",
        f"--pyi_out={OUT_DIR}",
        str(PROTO_DIR / "flow.proto"),
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)

    # grpc_tools generates `import flow_pb2` (absolute), which only works if
    # proto_gen is on sys.path directly. Rewrite to a relative import so it
    # works as part of the netflow_sentry.proto_gen package.
    grpc_file = OUT_DIR / "flow_pb2_grpc.py"
    text = grpc_file.read_text(encoding="utf-8")
    text = text.replace("import flow_pb2 as flow__pb2", "from . import flow_pb2 as flow__pb2")
    grpc_file.write_text(text, encoding="utf-8")

    print("Generated stubs in", OUT_DIR)


if __name__ == "__main__":
    main()
