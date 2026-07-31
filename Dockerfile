FROM python:3.12-slim

LABEL maintainer="viibeware"
LABEL description="Warehouse Manager — Parts Inventory System"

WORKDIR /app

# gosu lets the entrypoint drop from root to the app user after fixing up the
# data volume's ownership (see docker-entrypoint.sh).
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

# Unprivileged account the server actually runs as. Fixed uid so ownership of
# a bind-mounted data directory is predictable on the host.
RUN useradd --system --create-home --uid 10001 --shell /usr/sbin/nologin wm

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app.py .
COPY CHANGELOG.md .
COPY templates/ templates/
COPY static/ static/

# Create data directory
RUN mkdir -p /data/uploads/temp && chown -R wm:wm /data

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENV WM_DATA_DIR=/data
ENV PYTHONUNBUFFERED=1
# /app is owned by root and the server runs as wm, so bytecode caching there
# would fail anyway — skip the attempt.
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 5000

ENTRYPOINT ["docker-entrypoint.sh"]

# --timeout 300: the WordPress importer runs synchronously and may download many
# files in one request; the longer ceiling gives large imports headroom (and the
# importer is resumable via source_url dedup if it ever does time out).
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "3", "--timeout", "300", "app:app"]
