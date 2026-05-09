import ast
import os
import re
from urllib.parse import parse_qsl, unquote, urlparse
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-argus-local-dev-key-change-me-if-you-care',
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DJANGO_DEBUG', '1') not in {'0', 'false', 'False'}


def _env_list(name, default=''):
    value = os.environ.get(name, default)
    return [item.strip() for item in value.split(',') if item.strip()]


def _env_bool(name, default=False):
    fallback = '1' if default else '0'
    return os.environ.get(name, fallback) not in {'0', 'false', 'False'}


ALLOWED_HOSTS = _env_list('ARGUS_ALLOWED_HOSTS', '127.0.0.1,localhost')
CSRF_TRUSTED_ORIGINS = _env_list('ARGUS_CSRF_TRUSTED_ORIGINS')
USE_X_FORWARDED_HOST = _env_bool('ARGUS_USE_X_FORWARDED_HOST', True)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = _env_bool('ARGUS_SECURE_SSL_REDIRECT', not DEBUG)
SESSION_COOKIE_SECURE = _env_bool('ARGUS_SESSION_COOKIE_SECURE', not DEBUG)
CSRF_COOKIE_SECURE = _env_bool('ARGUS_CSRF_COOKIE_SECURE', not DEBUG)
SECURE_HSTS_SECONDS = int(os.environ.get('ARGUS_SECURE_HSTS_SECONDS', '31536000' if not DEBUG else '0'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool('ARGUS_SECURE_HSTS_INCLUDE_SUBDOMAINS', False)
SECURE_HSTS_PRELOAD = _env_bool('ARGUS_SECURE_HSTS_PRELOAD', False)


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'collector',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'collector.middleware.SingleActiveSessionMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'argus_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'argus_project.wsgi.application'


def _postgres_database_config(database_url):
    parsed = urlparse(database_url)
    if parsed.scheme not in {'postgres', 'postgresql'}:
        raise ValueError('ARGUS_DATABASE_URL must use postgres:// or postgresql://.')
    query_options = dict(parse_qsl(parsed.query))
    config = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': unquote(parsed.path.lstrip('/')),
        'USER': unquote(parsed.username or ''),
        'PASSWORD': unquote(parsed.password or ''),
        'HOST': parsed.hostname or '',
        'PORT': str(parsed.port or ''),
        'CONN_MAX_AGE': int(os.environ.get('ARGUS_DB_CONN_MAX_AGE', '60')),
    }
    options = {}
    schema_name = os.environ.get('ARGUS_DB_SCHEMA', '').strip()
    if schema_name:
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', schema_name):
            raise ValueError('ARGUS_DB_SCHEMA must be a valid PostgreSQL identifier.')
        options['options'] = f'-c search_path={schema_name},public'
    sslmode = os.environ.get('ARGUS_DB_SSLMODE', query_options.get('sslmode', '')).strip()
    if sslmode:
        options['sslmode'] = sslmode
    if options:
        config['OPTIONS'] = options
    return config


ARGUS_DATABASE_URL = os.environ.get('ARGUS_DATABASE_URL', '')
if ARGUS_DATABASE_URL:
    DATABASES = {'default': _postgres_database_config(ARGUS_DATABASE_URL)}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'zh-hans'

TIME_ZONE = 'Asia/Shanghai'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = os.environ.get('ARGUS_STATIC_URL', '/static/')
STATIC_ROOT = os.environ.get('ARGUS_STATIC_ROOT', BASE_DIR / 'staticfiles')
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

ARGUS_PREVIEW_CACHE_TTL_SECONDS = int(os.environ.get('ARGUS_PREVIEW_CACHE_TTL_SECONDS', '86400'))

if DEBUG:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
            'LOCATION': BASE_DIR / '.cache' / 'django',
            'TIMEOUT': ARGUS_PREVIEW_CACHE_TTL_SECONDS,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': os.environ.get('ARGUS_REDIS_URL', 'redis://127.0.0.1:6379/2'),
            'KEY_PREFIX': os.environ.get('ARGUS_CACHE_KEY_PREFIX', 'argus'),
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            },
            'TIMEOUT': ARGUS_PREVIEW_CACHE_TTL_SECONDS,
        }
    }

EMAIL_BACKEND = os.environ.get('ARGUS_EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.environ.get('ARGUS_EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('ARGUS_EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.environ.get('ARGUS_EMAIL_USE_TLS', '1') not in {'0', 'false', 'False'}
EMAIL_HOST_USER = os.environ.get('ARGUS_EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('ARGUS_EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('ARGUS_EMAIL_FROM', EMAIL_HOST_USER or 'noreply@cheaptoken.io')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


def _parse_login_code_windows(value, setting_name):
    windows = ast.literal_eval(value)
    if not isinstance(windows, (list, tuple)):
        raise ValueError(f'{setting_name} must be a list of 2-item tuples.')
    normalized = []
    for item in windows:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError(f'Each {setting_name} item must be a 2-item tuple.')
        seconds, limit = int(item[0]), int(item[1])
        if seconds <= 0 or limit <= 0:
            raise ValueError(f'{setting_name} seconds and limit must be positive integers.')
        normalized.append((seconds, limit))
    if not normalized:
        raise ValueError(f'{setting_name} must contain at least one window.')
    return normalized

ARGUS_HTTP_TIMEOUT_SECONDS = int(os.environ.get('ARGUS_HTTP_TIMEOUT_SECONDS', '10'))
ARGUS_LOGIN_CODE_TTL_SECONDS = int(os.environ.get('ARGUS_LOGIN_CODE_TTL_SECONDS', '600'))
ARGUS_LOGIN_CODE_RETENTION_SECONDS = int(os.environ.get('ARGUS_LOGIN_CODE_RETENTION_SECONDS', '2592000'))
ARGUS_LOGIN_CODE_COOLDOWN_SECONDS = int(os.environ.get('ARGUS_LOGIN_CODE_COOLDOWN_SECONDS', '60'))
_ARGUS_LOGIN_CODE_EMAIL_WINDOWS = os.environ.get('ARGUS_LOGIN_CODE_EMAIL_WINDOWS', os.environ.get('ARGUS_LOGIN_CODE_WINDOWS', '[(600, 3), (86400, 10)]'))
ARGUS_LOGIN_CODE_EMAIL_WINDOWS = _parse_login_code_windows(_ARGUS_LOGIN_CODE_EMAIL_WINDOWS, 'ARGUS_LOGIN_CODE_EMAIL_WINDOWS')
ARGUS_LOGIN_CODE_IP_WINDOWS = _parse_login_code_windows(os.environ.get('ARGUS_LOGIN_CODE_IP_WINDOWS', '[(600, 10), (3600, 30)]'), 'ARGUS_LOGIN_CODE_IP_WINDOWS')
ARGUS_LOGIN_CODE_MAX_ATTEMPTS = int(os.environ.get('ARGUS_LOGIN_CODE_MAX_ATTEMPTS', '5'))
ARGUS_MANUAL_FETCH_COOLDOWN_SECONDS = int(os.environ.get('ARGUS_MANUAL_FETCH_COOLDOWN_SECONDS', '3600'))
ARGUS_EPAY_ENABLED = os.environ.get('ARGUS_EPAY_ENABLED', '0') in {'1', 'true', 'True'}
ARGUS_EPAY_URL = os.environ.get('ARGUS_EPAY_URL', '')
ARGUS_EPAY_PID = os.environ.get('ARGUS_EPAY_PID', '')
ARGUS_EPAY_KEY = os.environ.get('ARGUS_EPAY_KEY', '')
ARGUS_EPAY_NOTIFY_URL = os.environ.get('ARGUS_EPAY_NOTIFY_URL', '')
ARGUS_EPAY_RETURN_URL = os.environ.get('ARGUS_EPAY_RETURN_URL', '')

ADMIN_SITE_HEADER = 'CheapToken'
ADMIN_SITE_TITLE = 'CheapToken Admin'
ADMIN_INDEX_TITLE = 'AI Relay Pricing Watch'
