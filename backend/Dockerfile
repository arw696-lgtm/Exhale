# Exhale backend — analytical core + FastAPI service
FROM python:3.11-slim

WORKDIR /app

# Install the package (src layout; sql/schema.sql ships as package data).
COPY pyproject.toml README.md ./
COPY src ./src
# llm included: the extractor no-ops without ANTHROPIC_API_KEY, but the SDK
# must be present or enabling the key later crash-loops the container.
RUN pip install --no-cache-dir ".[api,secure,pg,connectors,llm]"

EXPOSE 8000

# Liveness probe target: GET /health
CMD ["uvicorn", "exhale.api:app", "--host", "0.0.0.0", "--port", "8000"]
