# ---------------------------------------------------------------------------
# Azure RBAC Permission Graph Tool – Production Container Image
# ---------------------------------------------------------------------------
# Multi-stage build for a minimal, secure production image.
#
# Build:
#   docker build -t azure-rbac:latest .
#
# Run (dashboard):
#   docker run -p 5000:5000 azure-rbac:latest
#
# Run (graph builder):
#   docker run azure-rbac:latest azure-rbac build --output /data/graph.json
# ---------------------------------------------------------------------------

# ---- Stage 1: Build dependencies ----
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build-time system deps (gcc needed for some Azure SDK C extensions)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/

# Build wheel and install into a virtual environment
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip setuptools && \
    /opt/venv/bin/pip install --no-cache-dir .

# ---- Stage 2: Production runtime ----
FROM python:3.12-slim AS runtime

# Security: run as non-root user
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash appuser

# Copy only the virtual environment from builder (no build tools in prod)
COPY --from=builder /opt/venv /opt/venv

# Copy application source (templates, static assets)
COPY src/ /app/src/

WORKDIR /app

# Ensure the venv is on PATH
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Create data directory for graph/findings files (writable by appuser)
RUN mkdir -p /data && chown appuser:appuser /data

# Health check for container orchestrators
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/health')"]

# Drop privileges
USER appuser

EXPOSE 5000

# Default: run the dashboard with gunicorn for production
# Override CMD for graph-builder: ["azure-rbac", "build", "--output", "/data/graph.json"]
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "2", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "azure_rbac.dashboard.app:create_app()"]
