
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV APP_ENV=DEV
ENV APP_VERSION=1.0.0
ENV PORT=5000

# Install application dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create a non-root application user
RUN addgroup --system app && adduser --system --ingroup app app

# Copy application files with correct ownership
COPY --chown=app:app app.py .
COPY --chown=app:app static/ ./static/

# Run the application without root privileges
USER app

EXPOSE 5000

# Check application health from inside the container
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=2)" || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "app:app"]
