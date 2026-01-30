FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY apps /app/apps

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

ENV PYTHONPATH=/app:/app/src

CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]