FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Run as a non-root user (container security)
RUN useradd -m appuser && chown -R appuser /app
USER appuser
ENV PORT=8080
# Cloud Run injects $PORT. --proxy-headers makes the real client IP and the
# original https scheme visible (needed for rate limiting + HTTPS redirect).
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips="*"
