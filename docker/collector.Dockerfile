FROM python:3.12-slim AS base

WORKDIR /app

COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt grpcio-tools

COPY proto ./proto
COPY scripts ./scripts
COPY src ./src

RUN python scripts/generate_proto.py
RUN pip install --no-cache-dir -e .

EXPOSE 50051 9100

CMD ["python", "-m", "netflow_sentry.collector.main"]
