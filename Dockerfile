# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
	gosu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps zuerst (Layer-Cache)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Quellcode
COPY . .

# Non-root user
RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app

EXPOSE 8000

# Entrypoint führt migrate + collectstatic aus, dann startet gunicorn
ENTRYPOINT ["./scripts/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
