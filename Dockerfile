FROM python:3.12-slim

LABEL maintainer="viibeware"
LABEL description="Warehouse Manager — Parts Inventory System"

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app.py .
COPY CHANGELOG.md .
COPY templates/ templates/
COPY static/ static/

# Create data directory
RUN mkdir -p /data/uploads/temp

ENV WM_DATA_DIR=/data
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

# --timeout 300: the WordPress importer runs synchronously and may download many
# files in one request; the longer ceiling gives large imports headroom (and the
# importer is resumable via source_url dedup if it ever does time out).
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "3", "--timeout", "300", "app:app"]
