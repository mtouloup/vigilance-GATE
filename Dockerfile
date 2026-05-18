FROM python:3.11-slim

WORKDIR /app

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
