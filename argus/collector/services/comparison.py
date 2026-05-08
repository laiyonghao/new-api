from collections import defaultdict

from collector.models import CompetitorSite, FetchRun, ModelPriceSnapshot


def _read_query_value(query_params, key):
    return (query_params.get(key, '') or '').strip()


def _split_normalized_model_name_terms(value):
    return [term.strip() for term in (value or '').split() if term.strip()]


def _apply_normalized_model_name_filter(snapshots_queryset, normalized_model_name_query=None):
    for term in _split_normalized_model_name_terms(normalized_model_name_query):
        snapshots_queryset = snapshots_queryset.filter(normalized_model_name__icontains=term)
    return snapshots_queryset


def _get_latest_snapshots_queryset(quota_type=None):
    enabled_sites = list(CompetitorSite.objects.filter(enabled=True).only('id'))
    if not enabled_sites:
        return ModelPriceSnapshot.objects.none()

    latest_runs = {}
    for fetch_run in (
        FetchRun.objects.filter(site__enabled=True, status=FetchRun.Status.SUCCESS)
        .select_related('site')
        .order_by('site_id', '-finished_at', '-id')
    ):
        latest_runs.setdefault(fetch_run.site_id, fetch_run.id)

    if not latest_runs:
        return ModelPriceSnapshot.objects.none()

    snapshots_queryset = ModelPriceSnapshot.objects.filter(
        fetch_run_id__in=latest_runs.values(),
        site__enabled=True,
    )
    if quota_type is not None:
        snapshots_queryset = snapshots_queryset.filter(quota_type=quota_type)

    return snapshots_queryset


def get_vendor_choices(quota_type=None, normalized_model_name_query=None):
    snapshots = _get_latest_snapshots_queryset(quota_type=quota_type)
    snapshots = _apply_normalized_model_name_filter(
        snapshots,
        normalized_model_name_query=normalized_model_name_query,
    )

    seen = set()
    for snapshot in snapshots.only('vendor_name'):
        vendor_name = (snapshot.vendor_name or '').strip()
        if not vendor_name:
            continue
        seen.add(vendor_name)

    return [
        {'value': vendor_name, 'label': vendor_name}
        for vendor_name in sorted(seen, key=str.lower)
    ]


def build_comparison_context(query_params, all_label='全部'):
    quota_type_value = _read_query_value(query_params, 'quota_type')
    vendor_name_value = _read_query_value(query_params, 'vendor_name')
    normalized_model_name_query = _read_query_value(query_params, 'normalized_model_name')
    selected_quota_type = ''
    quota_type = None
    vendor_name = ''

    if quota_type_value in {
        str(ModelPriceSnapshot.QuotaType.TOKEN),
        str(ModelPriceSnapshot.QuotaType.REQUEST),
    }:
        selected_quota_type = quota_type_value
        quota_type = int(quota_type_value)

    vendor_choices = get_vendor_choices(
        quota_type=quota_type,
        normalized_model_name_query=normalized_model_name_query or None,
    )
    valid_vendor_values = {choice['value'] for choice in vendor_choices}
    if vendor_name_value in valid_vendor_values:
        vendor_name = vendor_name_value
    else:
        vendor_name_value = ''

    rows = build_comparison_rows(
        quota_type=quota_type,
        vendor_name=vendor_name or None,
        normalized_model_name_query=normalized_model_name_query or None,
    )

    return {
        'rows': rows,
        'row_count': len(rows),
        'quota_type_choices': [
            {'value': '', 'label': all_label},
            {'value': str(ModelPriceSnapshot.QuotaType.TOKEN), 'label': 'Token'},
            {'value': str(ModelPriceSnapshot.QuotaType.REQUEST), 'label': 'Request'},
        ],
        'vendor_choices': vendor_choices,
        'selected_quota_type': selected_quota_type,
        'selected_vendor_name': vendor_name_value,
        'normalized_model_name_query': normalized_model_name_query,
    }


def build_comparison_rows(quota_type=None, vendor_name=None, normalized_model_name_query=None):
    snapshots_queryset = _get_latest_snapshots_queryset(quota_type=quota_type)
    if vendor_name:
        snapshots_queryset = snapshots_queryset.filter(vendor_name=vendor_name)
    snapshots_queryset = _apply_normalized_model_name_filter(
        snapshots_queryset,
        normalized_model_name_query=normalized_model_name_query,
    )

    snapshots = (
        snapshots_queryset
        .select_related('site', 'fetch_run')
        .order_by('normalized_model_name', 'model_name', 'site__name', 'site__base_url')
    )

    grouped = defaultdict(list)
    for snapshot in snapshots:
        grouped[snapshot.normalized_model_name].append(snapshot)

    rows = []
    for normalized_model_name, items in grouped.items():
        vendor_names = sorted({item.vendor_name.strip() for item in items if (item.vendor_name or '').strip()}, key=str.lower)
        row = {
            'model_name': normalized_model_name,
            'vendor_name': ' / '.join(vendor_names) if vendor_names else '-',
            'quota_type': items[0].get_quota_type_display(),
            'input_site': None,
            'input_price': None,
            'input_supported_endpoint_types': [],
            'output_site': None,
            'output_price': None,
            'output_supported_endpoint_types': [],
            'request_site': None,
            'request_price': None,
            'request_supported_endpoint_types': [],
        }

        for item in items:
            if item.is_dynamic:
                continue
            if item.quota_type == ModelPriceSnapshot.QuotaType.TOKEN:
                if item.input_price_converted_per_1m is not None and (
                    row['input_price'] is None or item.input_price_converted_per_1m < row['input_price']
                ):
                    row['input_price'] = item.input_price_converted_per_1m
                    row['input_site'] = item.site
                    row['input_supported_endpoint_types'] = item.supported_endpoint_types
                if item.output_price_converted_per_1m is not None and (
                    row['output_price'] is None or item.output_price_converted_per_1m < row['output_price']
                ):
                    row['output_price'] = item.output_price_converted_per_1m
                    row['output_site'] = item.site
                    row['output_supported_endpoint_types'] = item.supported_endpoint_types
            elif item.request_price_converted is not None and (
                row['request_price'] is None or item.request_price_converted < row['request_price']
            ):
                row['request_price'] = item.request_price_converted
                row['request_site'] = item.site
                row['request_supported_endpoint_types'] = item.supported_endpoint_types

        if any(row[key] is not None for key in ('input_price', 'output_price', 'request_price')):
            rows.append(row)

    return rows