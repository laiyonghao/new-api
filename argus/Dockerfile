FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=argus_project.settings

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates

COPY argus/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY argus/ ./
RUN DJANGO_DEBUG=0 python manage.py collectstatic --noinput

RUN chmod +x /app/docker-entrypoint.sh \
    && useradd --create-home --shell /usr/sbin/nologin argus \
    && chown -R argus:argus /app

USER argus

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 CMD python -c "import urllib.request; request = urllib.request.Request('http://127.0.0.1:8000/', headers={'Host': 'ct.xhh.club', 'X-Forwarded-Proto': 'https'}); urllib.request.urlopen(request, timeout=5).read()" || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "argus_project.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-"]