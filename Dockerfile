FROM python:3.12-slim

LABEL maintainer="viibeware"
LABEL description="Warehouse Manager — Parts Inventory System"

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app.py .
COPY templates/ templates/
COPY static/ static/

# Create data directory
RUN mkdir -p /data/uploads/temp

ENV WM_DATA_DIR=/data
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "3", "--timeout", "120", "app:app"]
