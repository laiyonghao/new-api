import json
import secrets
from hashlib import sha256
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model, login, logout
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .models import CompetitorSite, FetchRun, LoginCode, ModelAlias, ModelPriceSnapshot, NormalizationSettings, PaymentOrder, UserPlanSubscription, UserSessionState, normalize_base_url, normalize_model_name
from .plans import DEFAULT_PLAN_CODE, get_plan, get_plan_price, site_usage_percent
from .services.comparison import build_comparison_context
from .services.discovery import discover_site_status_metadata
from .services.epay import build_payment_request, epay_is_configured, verify_callback
from .services.fetcher import collect_site_pricing, preview_site_pricing


_LATEST_FETCH_NOT_PROVIDED = object()
_PREVIEW_CACHE_VERSION = 'v1'

AUTH_REQUIRED_PAGES = {
	'watchlist/sites.html',
	'watchlist/comparison.html',
	'watchlist/custom-comparison.html',
	'watchlist/fetch-runs.html',
	'watchlist/rules.html',
	'account/account.html',
}


PAGE_TEMPLATES = {
	'index.html': 'collector/home.html',
	'watchlist/sites.html': 'collector/watchlist/sites.html',
	'watchlist/comparison.html': 'collector/watchlist/comparison.html',
	'watchlist/custom-comparison.html': 'collector/watchlist/custom_comparison.html',
	'watchlist/fetch-runs.html': 'collector/watchlist/fetch_runs.html',
	'watchlist/rules.html': 'collector/watchlist/rules.html',
	'pricing/billing.html': 'collector/pricing/billing.html',
	'account/account.html': 'collector/account/account.html',
}


PAGE_META = {
	'index.html': {'active_nav': 'home'},
	'watchlist/sites.html': {'active_nav': 'watchlist'},
	'watchlist/comparison.html': {'active_nav': 'watchlist'},
	'watchlist/custom-comparison.html': {'active_nav': 'watchlist'},
	'watchlist/fetch-runs.html': {'active_nav': 'watchlist'},
	'watchlist/rules.html': {'active_nav': 'watchlist'},
	'pricing/billing.html': {'active_nav': 'pricing'},
	'account/account.html': {'active_nav': 'account'},
}


def _safe_next_url(next_url, request):
	if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
		return next_url
	return reverse('watchlist_sites')


def _redirect_to_login(request):
	login_url = reverse('login')
	return redirect(f'{login_url}?{urlencode({"next": request.get_full_path()})}')


def _preview_cache_key(base_url):
	digest = sha256(base_url.encode('utf-8')).hexdigest()
	return f'argus:home-preview:{_PREVIEW_CACHE_VERSION}:{digest}'


def _build_preview_context(base_url):
	status_errors = []
	status_metadata = discover_site_status_metadata(base_url, errors=status_errors)
	preview_site = CompetitorSite(
		base_url=base_url,
		name=status_metadata.get('name', ''),
		icon_url=status_metadata.get('icon_url', ''),
		system_start_time=status_metadata.get('system_start_time'),
		system_version=status_metadata.get('system_version', ''),
		usd_exchange_rate=status_metadata.get('usd_exchange_rate') or Decimal('1.00'),
	)
	pricing_preview = preview_site_pricing(preview_site)
	return {
		'preview_site': preview_site,
		'pricing_preview': pricing_preview,
		'status_errors': status_errors,
	}


@ensure_csrf_cookie
def page_view(request, page='index.html'):
	template_name = PAGE_TEMPLATES.get(page)
	if template_name is None:
		raise Http404('Page not found')
	if page in AUTH_REQUIRED_PAGES and not request.user.is_authenticated:
		return _redirect_to_login(request)
	return render(request, template_name, _page_context(page, request))


def home_view(request):
	return page_view(request, 'index.html')


@require_POST
@ensure_csrf_cookie
def home_site_submit(request):
	base_url = (request.POST.get('base_url') or '').strip()
	if not base_url:
		return render(request, 'collector/home.html', {**_page_context('index.html', request), 'home_submit_error': '请输入站点网址。'}, status=400)

	if request.user.is_authenticated:
		success, result, status_code = _save_site_for_user(request, base_url=base_url, name='', posted_usd_exchange_rate=Decimal('1.00'))
		if success:
			return redirect('watchlist_sites')
		return render(request, 'collector/home.html', {**_page_context('index.html', request), 'home_submit_error': result}, status=status_code)

	try:
		base_url = normalize_base_url(base_url)
		cache_key = _preview_cache_key(base_url)
		preview_context = cache.get(cache_key)
		if preview_context is None:
			preview_context = _build_preview_context(base_url)
			cache.set(cache_key, preview_context, settings.ARGUS_PREVIEW_CACHE_TTL_SECONDS)
	except ValidationError as exc:
		return render(request, 'collector/home.html', {**_page_context('index.html', request), 'home_submit_error': _validation_message(exc)}, status=400)
	except Exception as exc:
		return render(request, 'collector/home.html', {**_page_context('index.html', request), 'home_submit_error': str(exc)}, status=400)

	preview_site = preview_context['preview_site']
	pricing_preview = preview_context['pricing_preview']

	return render(request, 'collector/site_preview.html', {
		'page_title': '站点能力预览',
		'active_nav': 'home',
		'preview_site': preview_site,
		'pricing_preview': pricing_preview,
		'status_errors': preview_context['status_errors'],
		'preview_rows': pricing_preview.snapshots[:20],
		'login_next_url': reverse('watchlist_sites'),
	})


def site_form_redirect(request):
	if not request.user.is_authenticated:
		return _redirect_to_login(request)
	return redirect('watchlist_sites')


@ensure_csrf_cookie
def login_view(request):
	next_url = _safe_next_url(request.GET.get('next'), request)
	if request.user.is_authenticated:
		return redirect(next_url)
	context = {
		'page_title': '注册/登入',
		'active_nav': 'account',
		'login_next_url': next_url,
	}
	return render(request, 'collector/account/login.html', context)


def comparison_view(request):
	context = {
		'page_title': '实时比价',
		'active_nav': 'watchlist',
		**build_comparison_context(request.GET, user=request.user if request.user.is_authenticated else None),
	}
	return render(request, 'collector/comparison.html', context)


@require_POST
def save_site(request):
	if not request.user.is_authenticated:
		return JsonResponse({'ok': False, 'message': '请先注册/登入后再管理 Watchlist。'}, status=401)
	site_id = (request.POST.get('site_id') or '').strip()
	base_url = (request.POST.get('base_url') or '').strip()
	name = (request.POST.get('name') or '').strip()
	posted_usd_exchange_rate = _parse_decimal(request.POST.get('usd_exchange_rate'), Decimal('1.00'))

	success, result, status_code = _save_site_for_user(request, base_url=base_url, name=name, posted_usd_exchange_rate=posted_usd_exchange_rate, site_id=site_id)
	if not success:
		return JsonResponse({'ok': False, 'message': result}, status=status_code)
	message, site = result

	return JsonResponse({'ok': True, 'message': message, 'site': _site_payload(site)})


@require_POST
def deactivate_site(request):
	if not request.user.is_authenticated:
		return JsonResponse({'ok': False, 'message': '请先注册/登入后再管理 Watchlist。'}, status=401)
	site = get_object_or_404(_site_queryset_for_user(request.user), pk=request.POST.get('site_id'))
	site.enabled = False
	site.save(update_fields=['enabled', 'updated_at'])
	return JsonResponse({'ok': True, 'message': '站点已移除出自动巡价，历史快照仍会保留。'})


@require_POST
def fetch_site(request):
	if not request.user.is_authenticated:
		return JsonResponse({'ok': False, 'message': '请先注册/登入后再管理 Watchlist。'}, status=401)
	site = get_object_or_404(_site_queryset_for_user(request.user), pk=request.POST.get('site_id'))
	if not site.enabled:
		return JsonResponse({'ok': False, 'message': '站点已暂停，不能执行手动采集。'}, status=400)
	cooldown_message = _manual_fetch_cooldown_message(site)
	if cooldown_message:
		return JsonResponse({'ok': False, 'message': cooldown_message}, status=429)
	fetch_run = collect_site_pricing(site)
	if fetch_run.status == FetchRun.Status.SUCCESS:
		message = f'采集成功：写入 {fetch_run.created_count} 个价格快照。'
	else:
		message = fetch_run.error_message or '采集失败，请稍后重试。'
	return JsonResponse({
		'ok': fetch_run.status == FetchRun.Status.SUCCESS,
		'message': message,
		'fetch_run': {
			'id': fetch_run.id,
			'status': fetch_run.status,
			'created_count': fetch_run.created_count,
			'http_status_code': fetch_run.http_status_code,
		},
	}, status=200 if fetch_run.status == FetchRun.Status.SUCCESS else 400)


@require_POST
def create_checkout_order(request):
	if not request.user.is_authenticated:
		return JsonResponse({'ok': False, 'message': '请先登录后再创建订单。'}, status=401)
	plan_code = (request.POST.get('plan_code') or '').strip().lower()
	billing_cycle = (request.POST.get('billing_cycle') or '').strip().lower()
	payment_method = (request.POST.get('payment_method') or 'epay').strip().lower()
	amount = get_plan_price(plan_code, billing_cycle)
	if amount is None:
		return JsonResponse({'ok': False, 'message': '请选择有效套餐和订阅周期。'}, status=400)
	trade_no = f'ARGUS-{timezone.localtime().strftime("%Y%m%d%H%M%S")}-{secrets.token_hex(3).upper()}'
	order = PaymentOrder.objects.create(
		user=request.user,
		trade_no=trade_no,
		payment_method=payment_method,
		plan_code=plan_code,
		billing_cycle=billing_cycle,
		amount_rmb=amount,
	)
	payment_url = ''
	if epay_is_configured():
		payment_payload, payment_url = build_payment_request(order, request)
		order.provider_payload_json = json.dumps(payment_payload, ensure_ascii=True)
		order.save(update_fields=['provider_payload_json', 'updated_at'])
	return JsonResponse({
		'ok': True,
		'message': '订单已创建。' if payment_url else '订单已创建。支付网关接入前，可先保留订单号用于调试。',
		'payment_url': payment_url,
		'payment_configured': bool(payment_url),
		'order': {
			'id': order.id,
			'trade_no': order.trade_no,
			'plan_code': order.plan_code,
			'billing_cycle': order.billing_cycle,
			'amount_rmb': str(order.amount_rmb),
			'status': order.status,
		},
	})


@csrf_exempt
@require_POST
def epay_notify(request):
	order = _verified_epay_order(request.POST.dict())
	if order is None:
		return HttpResponse('fail', status=400)
	_complete_payment_order(order)
	return HttpResponse('success')


def epay_return(request):
	order = _verified_epay_order(request.GET.dict())
	if order is not None and order.status == PaymentOrder.Status.PENDING:
		_complete_payment_order(order)
	return redirect('pricing_billing')


@require_POST
def save_normalization_rules(request):
	if not request.user.is_authenticated:
		return JsonResponse({'ok': False, 'message': '请先注册/登入后再管理规则。'}, status=401)
	default_exchange_rate = _parse_decimal(request.POST.get('default_usd_exchange_rate'), Decimal('7.20'))
	ranking_mode = (request.POST.get('ranking_mode') or '').strip()
	if ranking_mode not in NormalizationSettings.RankingMode.values:
		return JsonResponse({'ok': False, 'message': '请选择有效最低价口径。'}, status=400)
	settings_row = NormalizationSettings.current()
	settings_row.default_usd_exchange_rate = default_exchange_rate
	settings_row.ranking_mode = ranking_mode
	try:
		settings_row.save()
	except ValidationError as exc:
		return JsonResponse({'ok': False, 'message': _validation_message(exc)}, status=400)

	try:
		created_alias_count = _upsert_aliases_from_post(request)
	except ValidationError as exc:
		return JsonResponse({'ok': False, 'message': _validation_message(exc)}, status=400)
	refreshed_count = _refresh_snapshot_aliases()
	return JsonResponse({
		'ok': True,
		'message': f'归一化规则已保存，已同步 {refreshed_count} 条价格数据，新增或更新 {created_alias_count} 条别名。',
		'settings': {
			'default_usd_exchange_rate': str(settings_row.default_usd_exchange_rate),
			'ranking_mode': settings_row.ranking_mode,
		},
	})


@require_POST
def send_login_code(request):
	email = _normalize_email(request.POST.get('email'))
	if not email:
		return JsonResponse({'ok': False, 'message': '请输入有效邮箱。'}, status=400)

	rate_limit_message = _login_code_rate_limit_message(email, _client_ip(request))
	if rate_limit_message:
		return JsonResponse({'ok': False, 'message': rate_limit_message}, status=429)

	code = f'{secrets.randbelow(1000000):06d}'
	LoginCode.purge_stale()
	LoginCode.objects.filter(email=email, used_at__isnull=True).update(used_at=timezone.now())
	LoginCode.create_for_email(email=email, code=code, request_ip=_client_ip(request))
	_deliver_login_code(email, code)
	return JsonResponse({'ok': True, 'message': '验证码已发送，10 分钟内有效。'})


@require_POST
def verify_login_code(request):
	email = _normalize_email(request.POST.get('email'))
	code = (request.POST.get('code') or '').strip()
	if not email or not code:
		return JsonResponse({'ok': False, 'message': '请输入邮箱和验证码。'}, status=400)

	login_code = (
		LoginCode.objects.filter(email=email, used_at__isnull=True, expires_at__gt=timezone.now())
		.order_by('-created_at')
		.first()
	)
	if login_code is None:
		return JsonResponse({'ok': False, 'message': '验证码无效或已过期。'}, status=400)
	if not login_code.verify(code):
		if login_code.attempt_count < getattr(settings, 'ARGUS_LOGIN_CODE_MAX_ATTEMPTS', 5):
			login_code.register_failed_attempt()
		return JsonResponse({'ok': False, 'message': '验证码无效或已过期。'}, status=400)

	login_code.mark_used()
	user = _get_or_create_user(email)
	login(request, user)
	request.session.save()
	UserSessionState.objects.update_or_create(
		user=user,
		defaults={'active_session_key': request.session.session_key or ''},
	)
	return JsonResponse({'ok': True, 'message': '邮箱验证通过，当前会话已恢复。'})


def logout_view(request):
	if request.user.is_authenticated:
		UserSessionState.objects.filter(user=request.user).update(active_session_key='')
	logout(request)
	if request.method == 'POST':
		return JsonResponse({'ok': True, 'message': '已退出当前会话。'})
	return redirect('home')


def _normalize_email(value):
	email = (value or '').strip().lower()
	if not email:
		return ''
	try:
		validate_email(email)
	except ValidationError:
		return ''
	return email


def _client_ip(request):
	forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
	if forwarded_for:
		return forwarded_for.split(',', 1)[0].strip()
	return request.META.get('REMOTE_ADDR', '')


def _login_code_rate_limit_message(email, request_ip):
	now = timezone.now()
	cooldown_seconds = getattr(settings, 'ARGUS_LOGIN_CODE_COOLDOWN_SECONDS', 60)
	if LoginCode.objects.filter(email=email, created_at__gt=now - timedelta(seconds=cooldown_seconds)).exists():
		return '验证码发送太频繁，请稍后再试。'
	for window_seconds, window_limit in getattr(settings, 'ARGUS_LOGIN_CODE_EMAIL_WINDOWS', [(600, 3), (86400, 10)]):
		window_start = now - timedelta(seconds=window_seconds)
		if LoginCode.objects.filter(email=email, created_at__gt=window_start).count() >= window_limit:
			return '验证码请求次数过多，请稍后再试。'
	for window_seconds, window_limit in getattr(settings, 'ARGUS_LOGIN_CODE_IP_WINDOWS', [(600, 10), (3600, 30)]):
		window_start = now - timedelta(seconds=window_seconds)
		if request_ip and LoginCode.objects.filter(request_ip=request_ip, created_at__gt=window_start).count() >= window_limit:
			return '当前网络请求验证码过于频繁，请稍后再试。'
	return ''


def _manual_fetch_cooldown_message(site):
	cooldown = _manual_fetch_cooldown(site)
	if not cooldown['active']:
		return ''
	return f'手动采集过于频繁，请约 {cooldown["remaining_minutes"]} 分钟后再试。'


def _manual_fetch_cooldown(site, latest_started_at=_LATEST_FETCH_NOT_PROVIDED):
	cooldown_seconds = getattr(settings, 'ARGUS_MANUAL_FETCH_COOLDOWN_SECONDS', 3600)
	if cooldown_seconds <= 0:
		return {'active': False, 'remaining_seconds': 0, 'remaining_minutes': 0, 'available_at': None}
	if latest_started_at is _LATEST_FETCH_NOT_PROVIDED:
		latest_fetch = FetchRun.objects.filter(site=site).order_by('-started_at', '-id').only('started_at').first()
		latest_started_at = latest_fetch.started_at if latest_fetch else None
	if latest_started_at is None:
		return {'active': False, 'remaining_seconds': 0, 'remaining_minutes': 0, 'available_at': None}
	available_at = latest_started_at + timedelta(seconds=cooldown_seconds)
	now = timezone.now()
	if available_at <= now:
		return {'active': False, 'remaining_seconds': 0, 'remaining_minutes': 0, 'available_at': available_at}
	remaining_seconds = max(1, int((available_at - now).total_seconds()))
	remaining_minutes = max(1, (remaining_seconds + 59) // 60)
	return {
		'active': True,
		'remaining_seconds': remaining_seconds,
		'remaining_minutes': remaining_minutes,
		'available_at': available_at,
	}


def _email_is_configured():
	backend = getattr(settings, 'EMAIL_BACKEND', '')
	if backend and backend != 'django.core.mail.backends.smtp.EmailBackend':
		return True
	return bool(getattr(settings, 'EMAIL_HOST', '') and getattr(settings, 'DEFAULT_FROM_EMAIL', ''))


def _deliver_login_code(email, code):
	if not _email_is_configured():
		if settings.DEBUG:
			print(f'[CheapToken] Login code for {email}: {code}', flush=True)
			return
		raise RuntimeError('Email delivery is not configured.')

	send_mail(
		subject='CheapToken 登录验证码',
		message=f'你的 CheapToken 登录验证码是：{code}\n\n验证码 10 分钟内有效。',
		from_email=settings.DEFAULT_FROM_EMAIL,
		recipient_list=[email],
		fail_silently=False,
	)


def _get_or_create_user(email):
	User = get_user_model()
	user = User.objects.filter(email__iexact=email).first()
	if user is not None:
		return user

	username = email[:150]
	if User.objects.filter(username=username).exists():
		digest = sha256(email.encode('utf-8')).hexdigest()[:12]
		username = f'argus-{digest}'
	user = User(username=username, email=email)
	user.set_unusable_password()
	user.save()
	return user


def _page_context(page, request):
	context = {
		**PAGE_META.get(page, {}),
		**_navigation_context(request),
	}
	if page == 'watchlist/sites.html':
		context.update(_sites_context(request))
		return context
	if page == 'watchlist/comparison.html':
		context.update(_watchlist_comparison_context(request, use_request_filters=False))
		return context
	if page == 'watchlist/custom-comparison.html':
		context.update(_watchlist_comparison_context(request))
		return context
	if page == 'watchlist/fetch-runs.html':
		context.update(_fetch_runs_context(request))
		return context
	if page == 'watchlist/rules.html':
		context.update(_rules_context())
		return context
	if page == 'account/account.html':
		context.update(_account_context(request))
		return context
	return context


def _active_plan_for_user(user):
	if not user.is_authenticated:
		return get_plan(DEFAULT_PLAN_CODE), None
	subscription = UserPlanSubscription.objects.filter(user=user).first()
	if subscription is None or not subscription.is_active:
		return get_plan(DEFAULT_PLAN_CODE), subscription
	return get_plan(subscription.plan_code), subscription


def _navigation_context(request):
	plan, _subscription = _active_plan_for_user(request.user)
	return {'navigation_account_plan': plan}


def _site_queryset_for_user(user):
	if user is not None and user.is_authenticated:
		return CompetitorSite.objects.filter(owner=user)
	return CompetitorSite.objects.filter(owner__isnull=True)


def _rules_context():
	settings_row = NormalizationSettings.current()
	return {
		'normalization_settings': settings_row,
		'model_aliases': ModelAlias.objects.order_by('source_model_name'),
		'alias_count': ModelAlias.objects.filter(enabled=True).count(),
		'default_exchange_rate': settings_row.default_usd_exchange_rate,
		'ranking_mode': settings_row.ranking_mode,
		'ranking_mode_choices': NormalizationSettings.RankingMode.choices,
	}


def _upsert_aliases_from_post(request):
	sources = request.POST.getlist('alias_source')
	targets = request.POST.getlist('alias_target')
	notes = request.POST.getlist('alias_note')
	changed_count = 0
	for index, source in enumerate(sources):
		target = targets[index] if index < len(targets) else ''
		note = notes[index] if index < len(notes) else ''
		source_model_name = normalize_model_name(source)
		target_model_name = normalize_model_name(target)
		if not source_model_name and not target_model_name:
			continue
		if not source_model_name or not target_model_name:
			raise ValidationError('别名来源和目标模型都不能为空。')
		ModelAlias.objects.update_or_create(
			source_model_name=source_model_name,
			defaults={'target_model_name': target_model_name, 'note': note, 'enabled': True},
		)
		changed_count += 1
	return changed_count


def _refresh_snapshot_aliases():
	aliases = {
		alias.source_model_name: alias.target_model_name
		for alias in ModelAlias.objects.filter(enabled=True).only('source_model_name', 'target_model_name')
	}
	changed = []
	for snapshot in ModelPriceSnapshot.objects.only('id', 'model_name', 'normalized_model_name'):
		base_name = normalize_model_name(snapshot.model_name)
		normalized_model_name = aliases.get(base_name, base_name)
		if snapshot.normalized_model_name != normalized_model_name:
			snapshot.normalized_model_name = normalized_model_name
			changed.append(snapshot)
	if changed:
		ModelPriceSnapshot.objects.bulk_update(changed, ['normalized_model_name'])
	return len(changed)


def _can_enable_another_site(request):
	plan, _subscription = _active_plan_for_user(request.user)
	return _site_queryset_for_user(request.user).filter(enabled=True).count() < plan.site_limit


def _plan_limit_message(request):
	plan, _subscription = _active_plan_for_user(request.user)
	return f'当前 {plan.label} 套餐最多可启用 {plan.site_limit} 个站点，请先暂停旧站点或升级套餐。'


def _verified_epay_order(payload):
	if not verify_callback(payload):
		return None
	if payload.get('trade_status') not in {'TRADE_SUCCESS', 'TRADE_FINISHED'}:
		return None
	trade_no = payload.get('out_trade_no') or ''
	try:
		order = PaymentOrder.objects.get(trade_no=trade_no)
	except PaymentOrder.DoesNotExist:
		return None
	try:
		paid_amount = Decimal(str(payload.get('money') or '0'))
	except (InvalidOperation, TypeError, ValueError):
		return None
	if paid_amount != order.amount_rmb:
		return None
	return order


@transaction.atomic
def _complete_payment_order(order):
	locked_order = PaymentOrder.objects.select_for_update().select_related('user').get(pk=order.pk)
	if locked_order.status == PaymentOrder.Status.PAID:
		return locked_order
	locked_order.status = PaymentOrder.Status.PAID
	locked_order.paid_at = timezone.now()
	locked_order.save(update_fields=['status', 'paid_at', 'updated_at'])
	_extend_subscription(locked_order)
	return locked_order


def _extend_subscription(order):
	duration = _billing_cycle_duration(order.billing_cycle)
	now = timezone.now()
	subscription, _created = UserPlanSubscription.objects.get_or_create(
		user=order.user,
		defaults={
			'plan_code': order.plan_code,
			'status': UserPlanSubscription.Status.ACTIVE,
			'starts_at': now,
			'expires_at': now + duration,
		},
	)
	base_time = now if _created else subscription.expires_at if subscription.expires_at and subscription.expires_at > now else now
	subscription.plan_code = order.plan_code
	subscription.status = UserPlanSubscription.Status.ACTIVE
	subscription.starts_at = subscription.starts_at or now
	subscription.expires_at = base_time + duration
	subscription.save(update_fields=['plan_code', 'status', 'starts_at', 'expires_at', 'updated_at'])


def _billing_cycle_duration(billing_cycle):
	return {
		'month': timedelta(days=30),
		'quarter': timedelta(days=90),
		'year': timedelta(days=365),
	}.get(billing_cycle, timedelta(days=30))


def _account_context(request):
	plan, subscription = _active_plan_for_user(request.user)
	site_queryset = _site_queryset_for_user(request.user)
	enabled_site_count = site_queryset.filter(enabled=True).count()
	total_site_count = site_queryset.count()
	usage_percent = site_usage_percent(enabled_site_count, plan)
	if request.user.is_authenticated:
		email = request.user.email or request.user.username
		session_state = getattr(request.user, 'argus_session_state', None)
		active_session_key = session_state.active_session_key if session_state else ''
	else:
		email = '未登录'
		active_session_key = ''
	return {
		'account_email': email,
		'account_plan': plan,
		'account_subscription': subscription,
		'account_enabled_site_count': enabled_site_count,
		'account_total_site_count': total_site_count,
		'account_site_usage_percent': usage_percent,
		'account_session_label': '本设备' if request.user.is_authenticated else '未登录',
		'account_session_status': '在线' if request.user.is_authenticated else '离线',
		'account_active_session_key': active_session_key,
		'account_session_replaced': getattr(request, 'argus_session_replaced', False),
	}


def _sites_context(request):
	sites = list(_site_queryset_for_user(request.user).prefetch_related('snapshots'))
	latest_started_at_by_site = {}
	if sites:
		for fetch_run in FetchRun.objects.filter(site_id__in=[site.id for site in sites]).order_by('site_id', '-started_at', '-id').only('site_id', 'started_at'):
			latest_started_at_by_site.setdefault(fetch_run.site_id, fetch_run.started_at)
	for site in sites:
		site.snapshot_count = site.snapshots.count()
		site.status_label = _site_status_label(site)
		site.status_chip_class = _site_status_chip_class(site)
		site.last_fetch_label = _relative_time(site.last_fetch_at)
		cooldown = _manual_fetch_cooldown(site, latest_started_at_by_site.get(site.id))
		site.manual_fetch_cooldown_active = cooldown['active']
		site.manual_fetch_remaining_minutes = cooldown['remaining_minutes']
		site.manual_fetch_available_at = cooldown['available_at']
		site.manual_fetch_label = f'{cooldown["remaining_minutes"]} 分钟后可采集' if cooldown['active'] else '可立即执行'
		site.search_text = f'{site.name} {site.base_url} {site.note}'.lower()

	enabled_count = sum(1 for site in sites if site.enabled)
	healthy_count = sum(1 for site in sites if site.last_fetch_status == CompetitorSite.FetchStatus.SUCCESS and site.enabled)
	attention_count = sum(1 for site in sites if site.last_fetch_status == CompetitorSite.FetchStatus.FAILED or not site.enabled)
	return {
		'sites': sites,
		'site_total_count': len(sites),
		'site_enabled_count': enabled_count,
		'site_healthy_count': healthy_count,
		'site_attention_count': attention_count,
		'compare_limit': 3,
	}


def _watchlist_comparison_context(request, use_request_filters=True):
	context = build_comparison_context(request.GET if use_request_filters else {}, user=request.user)
	if not use_request_filters:
		quota_type_value = (request.GET.get('quota_type', '') or '').strip()
		vendor_name_value = (request.GET.get('vendor_name', '') or '').strip()
		context['normalized_model_name_query'] = (request.GET.get('normalized_model_name', '') or '').strip()
		context['selected_quota_type'] = quota_type_value if quota_type_value in {choice['value'] for choice in context['quota_type_choices']} else ''
		context['selected_vendor_name'] = vendor_name_value if vendor_name_value in {choice['value'] for choice in context['vendor_choices']} else ''
	rows = context['rows']
	context.update({
		'enabled_site_count': _site_queryset_for_user(request.user).filter(enabled=True).count(),
		'best_hit_count': sum(
			1
			for row in rows
			for price_key in ('input_price', 'output_price', 'request_price')
			if row.get(price_key) is not None
		),
	})
	return context


def _fetch_runs_context(request):
	runs = list(FetchRun.objects.filter(site__in=_site_queryset_for_user(request.user)).select_related('site').order_by('-started_at')[:50])
	for fetch_run in runs:
		fetch_run.started_label = timezone.localtime(fetch_run.started_at).strftime('%H:%M:%S') if fetch_run.started_at else '-'
		fetch_run.finished_label = timezone.localtime(fetch_run.finished_at).strftime('%H:%M:%S') if fetch_run.finished_at else '-'
		fetch_run.status_chip_class = _fetch_status_chip_class(fetch_run)
	return {
		'fetch_runs': runs,
		'today_success_count': FetchRun.objects.filter(site__in=_site_queryset_for_user(request.user), started_at__date=timezone.localdate(), status=FetchRun.Status.SUCCESS).count(),
		'latest_failed_count': FetchRun.objects.filter(site__in=_site_queryset_for_user(request.user), status=FetchRun.Status.FAILED).count(),
		'enabled_site_count': _site_queryset_for_user(request.user).filter(enabled=True).count(),
	}


def _site_payload(site):
	return {
		'id': site.id,
		'name': site.name or site.base_url,
		'base_url': site.base_url,
		'note': site.note,
		'enabled': site.enabled,
		'icon_url': site.icon_url,
		'system_start_time': site.system_start_time,
		'system_version': site.system_version,
		'usd_exchange_rate': str(site.usd_exchange_rate),
	}


def _save_site_for_user(request, *, base_url, name='', posted_usd_exchange_rate=None, site_id=''):
	if not base_url:
		return False, '请输入站点 Base URL。', 400

	try:
		base_url = normalize_base_url(base_url)
		if not site_id and not _can_enable_another_site(request):
			return False, _plan_limit_message(request), 400
		status_errors = []
		status_metadata = discover_site_status_metadata(base_url, errors=status_errors)
		status_rate = status_metadata.get('usd_exchange_rate')
		usd_exchange_rate = status_rate or posted_usd_exchange_rate or Decimal('1.00')
		resolved_name = name or status_metadata.get('name', '')
		if site_id:
			site = get_object_or_404(_site_queryset_for_user(request.user), pk=site_id)
			site.base_url = base_url
			site.name = resolved_name or site.name
			if status_metadata.get('icon_url'):
				site.icon_url = status_metadata['icon_url']
			site.system_start_time = status_metadata.get('system_start_time')
			site.system_version = status_metadata.get('system_version', '')
			site.usd_exchange_rate = usd_exchange_rate
			site.save()
			message = '站点档案已更新。'
		else:
			site = CompetitorSite.objects.create(
				owner=request.user,
				base_url=base_url,
				name=resolved_name,
				icon_url=status_metadata.get('icon_url', ''),
				system_start_time=status_metadata.get('system_start_time'),
				system_version=status_metadata.get('system_version', ''),
				enabled=True,
				usd_exchange_rate=usd_exchange_rate,
			)
			message = '站点已添加。'
		fetch_run = collect_site_pricing(site)
		if fetch_run.status == FetchRun.Status.SUCCESS:
			message = f'{message} 已同步 {fetch_run.created_count} 条价格数据。'
		else:
			message = f'{message} 但价格采集失败：{fetch_run.error_message or "请稍后重试。"}'
	except ValidationError as exc:
		return False, _validation_message(exc), 400
	except Exception as exc:
		return False, str(exc), 400

	return True, (message, site), 200


def _parse_decimal(value, default):
	try:
		return Decimal(str(value or default))
	except (InvalidOperation, TypeError, ValueError):
		return default


def _validation_message(exc):
	if hasattr(exc, 'message_dict'):
		messages = []
		for field_messages in exc.message_dict.values():
			messages.extend(field_messages)
		return ' '.join(messages)
	return ' '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)


def _site_status_label(site):
	if not site.enabled:
		return '静默'
	if site.last_fetch_status == CompetitorSite.FetchStatus.SUCCESS:
		return '健康'
	if site.last_fetch_status == CompetitorSite.FetchStatus.FAILED:
		return '失败'
	return '待采集'


def _site_status_chip_class(site):
	if not site.enabled:
		return 'border-[#e6e6e6] bg-slate-100 text-[#737373]'
	if site.last_fetch_status == CompetitorSite.FetchStatus.SUCCESS:
		return 'argus-chip-success'
	if site.last_fetch_status == CompetitorSite.FetchStatus.FAILED:
		return 'argus-chip-danger'
	return 'argus-chip-info'


def _fetch_status_chip_class(fetch_run):
	if fetch_run.status == FetchRun.Status.SUCCESS:
		return 'argus-chip-success'
	if fetch_run.status == FetchRun.Status.FAILED:
		return 'argus-chip-danger'
	return 'argus-chip-info'


def _relative_time(value):
	if value is None:
		return '从未采集'
	delta = timezone.now() - value
	minutes = int(delta.total_seconds() // 60)
	if minutes < 1:
		return '刚刚'
	if minutes < 60:
		return f'{minutes} 分钟前'
	hours = minutes // 60
	if hours < 24:
		return f'{hours} 小时前'
	return f'{hours // 24} 天前'
