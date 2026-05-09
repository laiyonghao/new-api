import json
from types import SimpleNamespace
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from collector.models import CompetitorSite, FetchRun, ModelAlias, ModelPriceSnapshot, normalize_model_name


ZERO = Decimal('0')
TWO = Decimal('2')


def _to_decimal(value):
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _truncate(text: str, limit: int = 2000) -> str:
    text = text or ''
    return text[:limit]


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _build_vendor_lookup(payload: dict):
    lookup = {}
    vendors = payload.get('vendors') or []
    if not isinstance(vendors, list):
        return lookup
    for vendor in vendors:
        if not isinstance(vendor, dict):
            continue
        remote_vendor_id = _to_int(vendor.get('id'))
        vendor_name = (vendor.get('name') or '').strip()
        if remote_vendor_id is None or not vendor_name:
            continue
        lookup[remote_vendor_id] = vendor_name
    return lookup


def _get_visible_group_ratio(item: dict, payload: dict) -> Decimal:
    group_ratio = payload.get('group_ratio') or {}
    usable_group = payload.get('usable_group') or {}
    enable_groups = item.get('enable_groups') or []

    if not enable_groups or 'all' in enable_groups:
        candidates = []
        for key in group_ratio.keys():
            if not usable_group or key in usable_group:
                ratio = _to_decimal(group_ratio.get(key))
                if ratio and ratio > 0:
                    candidates.append(ratio)
        return min(candidates) if candidates else Decimal('1')

    candidates = []
    for group in enable_groups:
        if usable_group and group not in usable_group:
            continue
        ratio = _to_decimal(group_ratio.get(group))
        if ratio and ratio > 0:
            candidates.append(ratio)
    return min(candidates) if candidates else Decimal('1')


def _normalize_snapshot(
    site: CompetitorSite,
    fetch_run: FetchRun,
    item: dict,
    payload: dict,
    vendor_lookup: dict,
    alias_lookup: dict,
    snapshot_at,
):
    model_name = (item.get('model_name') or '').strip()
    if not model_name:
        return None

    remote_vendor_id = _to_int(item.get('vendor_id'))
    vendor_name = vendor_lookup.get(remote_vendor_id, '') if remote_vendor_id is not None else ''
    quota_type = int(item.get('quota_type') or 0)
    billing_mode = (item.get('billing_mode') or '').strip()
    billing_expr = (item.get('billing_expr') or '').strip()
    supported_endpoint_types = item.get('supported_endpoint_types') or []
    if not isinstance(supported_endpoint_types, list):
        supported_endpoint_types = []
    group_ratio = _get_visible_group_ratio(item, payload)
    exchange_rate = _to_decimal(site.usd_exchange_rate) or Decimal('1')
    usd_multiplier = group_ratio
    converted_multiplier = group_ratio * exchange_rate

    model_ratio = _to_decimal(item.get('model_ratio'))
    completion_ratio = _to_decimal(item.get('completion_ratio'))
    model_price = _to_decimal(item.get('model_price'))
    cache_ratio = _to_decimal(item.get('cache_ratio'))
    create_cache_ratio = _to_decimal(item.get('create_cache_ratio'))

    input_price = None
    output_price = None
    request_price = None
    input_price_converted = None
    output_price_converted = None
    request_price_converted = None

    if not billing_mode and not billing_expr:
        if quota_type == ModelPriceSnapshot.QuotaType.TOKEN and model_ratio is not None:
            input_price = model_ratio * TWO * usd_multiplier
            output_multiplier = completion_ratio if completion_ratio is not None else Decimal('1')
            output_price = input_price * output_multiplier
            input_price_converted = model_ratio * TWO * converted_multiplier
            output_price_converted = input_price_converted * output_multiplier
        elif quota_type == ModelPriceSnapshot.QuotaType.REQUEST and model_price is not None:
            request_price = model_price * usd_multiplier
            request_price_converted = model_price * converted_multiplier

    base_model_name = normalize_model_name(model_name)
    normalized_model_name = alias_lookup.get(base_model_name, base_model_name)

    return ModelPriceSnapshot(
        fetch_run=fetch_run,
        site=site,
        model_name=model_name,
        normalized_model_name=normalized_model_name,
        vendor_name=vendor_name,
        quota_type=quota_type,
        input_price_usd_per_1m=input_price,
        output_price_usd_per_1m=output_price,
        request_price_usd=request_price,
        input_price_converted_per_1m=input_price_converted,
        output_price_converted_per_1m=output_price_converted,
        request_price_converted=request_price_converted,
        raw_model_ratio=model_ratio,
        raw_completion_ratio=completion_ratio,
        raw_model_price=model_price,
        raw_cache_ratio=cache_ratio,
        raw_create_cache_ratio=create_cache_ratio,
        billing_mode=billing_mode,
        billing_expr=billing_expr,
        supported_endpoint_types_json=json.dumps(supported_endpoint_types, ensure_ascii=True),
        raw_enable_groups_json=json.dumps(item.get('enable_groups') or [], ensure_ascii=True),
        snapshot_at=snapshot_at,
    )


def _fetch_pricing_payload(requested_url: str):
    response = requests.get(
        requested_url,
        timeout=settings.ARGUS_HTTP_TIMEOUT_SECONDS,
        headers={'User-Agent': 'CheapToken/0.1'},
    )
    response_excerpt = _truncate(response.text)
    if not response.ok:
        raise RuntimeError(f'HTTP {response.status_code}')

    payload = response.json()
    if not payload.get('success'):
        raise RuntimeError(payload.get('message') or 'Remote API returned success=false')

    items = payload.get('data')
    if not isinstance(items, list):
        raise RuntimeError('Remote pricing payload has no list data field')

    return response.status_code, response_excerpt, payload, items


def _build_snapshots(site: CompetitorSite, fetch_run: FetchRun, payload: dict, items: list, snapshot_at):
    vendor_lookup = _build_vendor_lookup(payload)
    alias_lookup = {
        alias.source_model_name: alias.target_model_name
        for alias in ModelAlias.objects.filter(enabled=True).only('source_model_name', 'target_model_name')
    }
    snapshots = []
    for item in items:
        if not isinstance(item, dict):
            continue
        snapshot = _normalize_snapshot(
            site,
            fetch_run,
            item,
            payload,
            vendor_lookup,
            alias_lookup,
            snapshot_at,
        )
        if snapshot is not None:
            snapshots.append(snapshot)
    return snapshots


def preview_site_pricing(site: CompetitorSite):
    requested_url = urljoin(site.base_url + '/', 'api/pricing')
    preview = SimpleNamespace(
        status=FetchRun.Status.RUNNING,
        requested_url=requested_url,
        http_status_code=None,
        response_excerpt='',
        created_count=0,
        error_message='',
        finished_at=None,
        snapshots=[],
    )

    try:
        http_status_code, response_excerpt, payload, items = _fetch_pricing_payload(requested_url)
        preview.http_status_code = http_status_code
        preview.response_excerpt = response_excerpt
        preview.finished_at = timezone.now()
        fetch_run = FetchRun(site=site, requested_url=requested_url, status=FetchRun.Status.SUCCESS, finished_at=preview.finished_at)
        preview.snapshots = _build_snapshots(site, fetch_run, payload, items, preview.finished_at)
        preview.status = FetchRun.Status.SUCCESS
        preview.created_count = len(preview.snapshots)
    except Exception as exc:
        preview.status = FetchRun.Status.FAILED
        preview.error_message = str(exc)
        preview.finished_at = timezone.now()

    return preview


@transaction.atomic
def collect_site_pricing(site: CompetitorSite) -> FetchRun:
    requested_url = urljoin(site.base_url + '/', 'api/pricing')
    fetch_run = FetchRun.objects.create(site=site, requested_url=requested_url)
    finished_at = None

    try:
        http_status_code, response_excerpt, payload, items = _fetch_pricing_payload(requested_url)
        fetch_run.http_status_code = http_status_code
        fetch_run.response_excerpt = response_excerpt
        finished_at = timezone.now()
        snapshots = _build_snapshots(site, fetch_run, payload, items, finished_at)

        ModelPriceSnapshot.objects.bulk_create(snapshots)

        fetch_run.status = FetchRun.Status.SUCCESS
        fetch_run.created_count = len(snapshots)
        fetch_run.error_message = ''
        site.last_fetch_status = CompetitorSite.FetchStatus.SUCCESS
        site.last_error = ''
    except Exception as exc:
        fetch_run.status = FetchRun.Status.FAILED
        fetch_run.error_message = str(exc)
        site.last_fetch_status = CompetitorSite.FetchStatus.FAILED
        site.last_error = str(exc)
    finally:
        now = finished_at or timezone.now()
        fetch_run.finished_at = now
        fetch_run.save()
        site.last_fetch_at = now
        site.save(update_fields=['last_fetch_at', 'last_fetch_status', 'last_error', 'updated_at'])

    return fetch_run