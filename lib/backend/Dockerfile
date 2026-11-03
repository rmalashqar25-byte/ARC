FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHON_DOTENV_DISABLED=1 ARC_ENVIRONMENT=production ARC_AGENT_WORKSPACE_ROOT=/data
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --system --uid 10001 arc && mkdir /data && chown arc:arc /data
COPY *.py ./
COPY company/ ./company/
USER 10001:10001
EXPOSE 8000
# Only trust forwarding headers from the local reverse proxy by default.
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "128", "--timeout-keep-alive", "5", "--forwarded-allow-ips", "127.0.0.1"]
