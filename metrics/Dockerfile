FROM python:3.12-slim

# Install curl for health check probe; clean apt cache to keep image small
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Create a dedicated non-root user with an explicit numeric UID so the
# container identity is predictable and auditable in runtime audit logs.
RUN groupadd --gid 1001 metrics \
    && useradd --uid 1001 --gid 1001 --no-create-home --shell /sbin/nologin metrics

WORKDIR /app

# Copy the dependency manifest first so Docker's layer cache is only
# invalidated when dependencies change, not on every source file edit.
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source after dependencies to exploit the cached pip layer.
COPY src/ .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 CMD curl -f http://localhost:8000/healthz || exit 1

USER metrics

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
