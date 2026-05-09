import hashlib
from urllib.parse import urlencode, urljoin

from django.conf import settings
from django.urls import reverse


SIGN_TYPE = 'MD5'


def epay_is_configured():
    return bool(
        getattr(settings, 'ARGUS_EPAY_ENABLED', False)
        and getattr(settings, 'ARGUS_EPAY_URL', '')
        and getattr(settings, 'ARGUS_EPAY_PID', '')
        and getattr(settings, 'ARGUS_EPAY_KEY', '')
    )


def _build_callback_url(request, setting_name, route_name):
    configured_url = getattr(settings, setting_name, '')
    if configured_url:
        return configured_url
    return request.build_absolute_uri(reverse(route_name))


def _sign(params):
    unsigned = '&'.join(
        f'{key}={params[key]}'
        for key in sorted(params.keys())
        if params[key] != '' and key not in {'sign', 'sign_type'}
    )
    return hashlib.md5((unsigned + getattr(settings, 'ARGUS_EPAY_KEY', '')).encode('utf-8')).hexdigest()


def build_payment_request(order, request):
    payment_type = order.payment_method if order.payment_method in {'alipay', 'wxpay', 'qqpay'} else 'alipay'
    params = {
        'pid': getattr(settings, 'ARGUS_EPAY_PID', ''),
        'type': payment_type,
        'out_trade_no': order.trade_no,
        'notify_url': _build_callback_url(request, 'ARGUS_EPAY_NOTIFY_URL', 'epay_notify'),
        'return_url': _build_callback_url(request, 'ARGUS_EPAY_RETURN_URL', 'epay_return'),
        'name': f'CheapToken {order.plan_code} {order.billing_cycle}',
        'money': f'{order.amount_rmb:.2f}',
    }
    params['sign'] = _sign(params)
    params['sign_type'] = SIGN_TYPE
    base_url = getattr(settings, 'ARGUS_EPAY_URL', '').rstrip('/') + '/'
    payment_url = urljoin(base_url, 'submit.php') + '?' + urlencode(params)
    return params, payment_url


def verify_callback(params):
    expected = _sign(params)
    return (params.get('sign') or '').lower() == expected.lower()
