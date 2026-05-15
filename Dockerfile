FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer cache)
COPY pyproject.toml .
RUN pip install --no-cache-dir pika>=1.3 pydantic>=2.0 pyyaml>=6.0 requests>=2.31

# Copy source
COPY vigilance/ vigilance/
COPY profiles/ profiles/

# Install package in editable mode
RUN pip install --no-cache-dir -e . --no-deps

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "vigilance.service"]
