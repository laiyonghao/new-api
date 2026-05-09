# Argus

Argus is a tiny Django + SQLite admin tool for tracking pricing from competitor new-api instances.

## Quick Start

Install dependencies if needed:

```bash
cd argus
../.venv/bin/python -m pip install -r requirements.txt
```

Apply migrations:

```bash
cd argus
../.venv/bin/python manage.py migrate
```

Create an admin user:

```bash
cd argus
../.venv/bin/python manage.py createsuperuser
```

Run the server:

```bash
cd argus
../.venv/bin/python manage.py runserver
```

Then open:

- http://127.0.0.1:8000/admin/

## Server Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for Docker, Postgres, Redis, nginx, CDN/ESA, SMTP, and Epay production deployment steps.

## Current Features

- Add a competitor by URL only.
- Auto-discover site name, note, and icon when possible.
- Auto-collect once on create.
- Collect selected sites or all enabled sites from Django Admin.
- Store fetch history and per-model pricing snapshots.
- Show cheapest competitor by model in a read-only admin comparison page.

## Notes

- This version only supports competitor sites that are compatible new-api instances.
- Pricing collection only uses the public /api/pricing endpoint.
- Dynamic billing expressions are stored but excluded from cheapest-price ranking.