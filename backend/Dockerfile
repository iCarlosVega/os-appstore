FROM python:3.14-slim-bookworm
ARG POSTGRES_MAJOR=17
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl --fail -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && echo 'deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main' > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-${POSTGRES_MAJOR} \
    && apt-get purge -y curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/app ./backend/app
COPY backend/alembic.ini ./backend/alembic.ini
COPY backend/alembic ./backend/alembic
COPY migrations ./migrations
ENV APP_ENV=production PYTHONUNBUFFERED=1 PORT=8000 BACKUP_DIR=/app/.data/backups
RUN useradd --create-home --uid 10001 store && mkdir -p /app/.data/backups && chown -R store:store /app/.data
USER store
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}"]
