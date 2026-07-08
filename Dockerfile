FROM python:3.11-slim

WORKDIR /app

# Install OPA for Rego policy validation (single static binary, no runtime deps)
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -L -o /usr/local/bin/opa \
       https://openpolicyagent.org/downloads/latest/opa_linux_amd64_static \
    && chmod +x /usr/local/bin/opa \
    && opa version \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

# Install all declared dependencies from pyproject.toml in one layer
COPY pyproject.toml .
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" pika "pydantic>=2.0" pyyaml requests

# Copy source
COPY vigilance/ vigilance/
COPY profiles/ profiles/
COPY schemas/ schemas/

# Install package
RUN pip install --no-cache-dir -e . --no-deps

ENV PYTHONUNBUFFERED=1

# Starts the broker consumer service + REST API server
CMD ["python", "-m", "vigilance.main"]
