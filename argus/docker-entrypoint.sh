#!/bin/sh
set -eu

python - <<'PY'
import os
import re
import time
from urllib.parse import urlparse, urlunparse

import psycopg
from psycopg import errors
from psycopg import sql

database_url = os.environ.get('ARGUS_DATABASE_URL', '')
schema_name = os.environ.get('ARGUS_DB_SCHEMA', '').strip()


def build_maintenance_url(target_url):
    parsed = urlparse(target_url)
    maintenance_db = os.environ.get('ARGUS_POSTGRES_MAINTENANCE_DB', 'postgres')
    return urlunparse(parsed._replace(path=f'/{maintenance_db}', query=''))


def ensure_database(target_url):
    parsed = urlparse(target_url)
    database_name = parsed.path.lstrip('/')
    if not database_name:
        return
    try:
        with psycopg.connect(target_url, autocommit=True):
            return
    except errors.InvalidCatalogName:
        pass
    maintenance_url = build_maintenance_url(target_url)
    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1 FROM pg_database WHERE datname = %s', (database_name,))
            if cursor.fetchone() is None:
                cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database_name)))

if database_url:
    last_error = None
    for attempt in range(1, 31):
        try:
            ensure_database(database_url)
            if not schema_name:
                break
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', schema_name):
                raise SystemExit('ARGUS_DB_SCHEMA must be a valid PostgreSQL identifier.')
            with psycopg.connect(database_url, autocommit=True) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(schema_name))
                    )
            break
        except psycopg.OperationalError as error:
            last_error = error
            print(f'Waiting for PostgreSQL before preparing Argus database ({attempt}/30)...', flush=True)
            time.sleep(2)
    else:
        raise SystemExit(f'PostgreSQL is not available: {last_error}')
PY

exec "$@"