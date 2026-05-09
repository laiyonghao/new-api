from html.parser import HTMLParser
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

import requests
from django.conf import settings


class HomePageMetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._inside_title = False
        self.title = ''
        self.description = ''
        self.icon_href = ''

    def handle_starttag(self, tag, attrs):
        attrs_map = {key.lower(): value for key, value in attrs}
        if tag.lower() == 'title':
            self._inside_title = True
            return

        if tag.lower() != 'meta' and tag.lower() != 'link':
            return

        if tag.lower() == 'meta':
            name = (attrs_map.get('name') or attrs_map.get('property') or '').lower()
            content = (attrs_map.get('content') or '').strip()
            if not self.description and content and name in {'description', 'og:description'}:
                self.description = content
            return

        rel = (attrs_map.get('rel') or '').lower()
        href = (attrs_map.get('href') or '').strip()
        if href and 'icon' in rel and not self.icon_href:
            self.icon_href = href

    def handle_endtag(self, tag):
        if tag.lower() == 'title':
            self._inside_title = False

    def handle_data(self, data):
        if self._inside_title:
            self.title += data


def _safe_get(url: str):
    return requests.get(
        url,
        timeout=settings.ARGUS_HTTP_TIMEOUT_SECONDS,
        headers={'User-Agent': 'CheapToken/0.1'},
    )


def _to_decimal(value):
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def discover_site_status_metadata(base_url: str, errors=None) -> dict:
    errors = errors if errors is not None else []
    metadata = {
        'name': '',
        'icon_url': '',
        'system_start_time': None,
        'system_version': '',
        'usd_exchange_rate': None,
    }

    status_url = urljoin(base_url + '/', 'api/status')
    try:
        response = _safe_get(status_url)
        if not response.ok:
            errors.append(f'/api/status returned HTTP {response.status_code}')
            return metadata
        payload = response.json()
        data = payload.get('data') or {}
        if not isinstance(data, dict):
            errors.append('/api/status returned invalid data')
            return metadata
        metadata['name'] = (data.get('system_name') or '').strip()
        logo = (data.get('logo') or '').strip()
        if logo:
            metadata['icon_url'] = urljoin(base_url + '/', logo)
        metadata['system_start_time'] = _to_int(data.get('start_time'))
        metadata['system_version'] = (data.get('version') or '').strip()
        exchange_rate = _to_decimal(data.get('custom_currency_exchange_rate'))
        if exchange_rate and exchange_rate > 0:
            metadata['usd_exchange_rate'] = exchange_rate
    except Exception as exc:
        errors.append(f'/api/status failed: {exc}')

    return metadata


def discover_site_metadata(base_url: str, errors=None, include_status: bool = True) -> dict:
    errors = errors if errors is not None else []
    metadata = {
        'name': '',
        'note': '',
        'icon_url': '',
    }

    if include_status:
        metadata.update({key: value for key, value in discover_site_status_metadata(base_url, errors).items() if key in metadata})

    page_url = urljoin(base_url + '/', '')
    parser = HomePageMetadataParser()
    try:
        response = _safe_get(page_url)
        if response.ok:
            parser.feed(response.text)
            if not metadata['name']:
                metadata['name'] = parser.title.strip()
            if not metadata['note']:
                metadata['note'] = parser.description.strip()
            if not metadata['icon_url'] and parser.icon_href:
                metadata['icon_url'] = urljoin(base_url + '/', parser.icon_href)
        else:
            errors.append(f'/ returned HTTP {response.status_code}')
    except Exception as exc:
        errors.append(f'/ failed: {exc}')

    if not metadata['icon_url']:
        favicon_url = urljoin(base_url + '/', 'favicon.ico')
        try:
            response = _safe_get(favicon_url)
            if response.ok:
                metadata['icon_url'] = favicon_url
            else:
                errors.append(f'/favicon.ico returned HTTP {response.status_code}')
        except Exception as exc:
            errors.append(f'/favicon.ico failed: {exc}')

    return metadata