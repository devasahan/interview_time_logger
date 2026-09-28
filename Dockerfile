FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN DJANGO_SECRET_KEY=collectstatic-only python manage.py collectstatic --noinput \
    && useradd --create-home app \
    && chown -R app /app
USER app

EXPOSE 8000
CMD ["sh", "docker-entrypoint.sh"]
