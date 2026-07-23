FROM python:3.12-slim

WORKDIR /app

# Install system deps for argon2 (already bundled in argon2-cffi, but keep for safety)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY breachelens/ ./breachelens/
COPY migrations/ ./migrations/
COPY data/ ./data/

# Install the package
RUN pip install --no-cache-dir -e ".[dev]"

# Environment defaults (override at runtime)
ENV BREACHLENS__SERVER__BIND_ADDR=0.0.0.0
ENV BREACHLENS__SERVER__PORT=8443

EXPOSE 8443

CMD ["python", "-m", "breachelens.main"]
