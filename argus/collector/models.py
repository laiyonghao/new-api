from decimal import Decimal
from datetime import timedelta
import re
import json
from urllib.parse import urlparse

from django.contrib.auth.hashers import check_password, make_password
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


BRACKET_SEGMENT_RE = re.compile(r'\[[^\[\]]*\]')
MODEL_VERSION_SEGMENT_RE = re.compile(r'-(?:latest|\d{8})(?=-|$)', re.IGNORECASE)
MULTI_HYPHEN_RE = re.compile(r'-{2,}')


def normalize_base_url(value: str) -> str:
	raw_value = (value or '').strip()
	if not raw_value:
		raise ValidationError('Base URL is required.')

	if '://' not in raw_value:
		raw_value = f'https://{raw_value}'

	parsed = urlparse(raw_value)
	if not parsed.scheme or not parsed.netloc:
		raise ValidationError('Enter a valid site URL.')

	scheme = parsed.scheme.lower()
	hostname = (parsed.hostname or '').lower()
	if not hostname:
		raise ValidationError('Enter a valid site URL.')

	port = parsed.port
	default_port = (scheme == 'http' and port == 80) or (scheme == 'https' and port == 443)
	netloc = hostname if port is None or default_port else f'{hostname}:{port}'
	return f'{scheme}://{netloc}'


def normalize_model_name(value: str) -> str:
	raw_value = (value or '').strip()
	if not raw_value:
		return ''
	cleaned = BRACKET_SEGMENT_RE.sub('', raw_value)
	cleaned = cleaned.replace('.', '-')
	cleaned = MODEL_VERSION_SEGMENT_RE.sub('', cleaned)
	cleaned = MULTI_HYPHEN_RE.sub('-', cleaned)
	cleaned = cleaned.strip(' -')
	return cleaned.strip() or raw_value


class CompetitorSite(models.Model):
	class FetchStatus(models.TextChoices):
		NEVER = 'never', 'Never'
		SUCCESS = 'success', 'Success'
		FAILED = 'failed', 'Failed'

	owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='argus_competitor_sites', null=True, blank=True)
	base_url = models.URLField(max_length=255)
	name = models.CharField(max_length=120, blank=True)
	note = models.TextField(blank=True)
	icon_url = models.URLField(max_length=500, blank=True)
	system_start_time = models.BigIntegerField(null=True, blank=True)
	system_version = models.CharField(max_length=120, blank=True)
	usd_exchange_rate = models.DecimalField(
		max_digits=12,
		decimal_places=6,
		default=Decimal('1.0'),
		help_text='RMB needed to buy 1 USD of credit. Examples: 1 = 1 RMB for 1 USD, 2 = 2 RMB for 1 USD, 0.6 = 0.6 RMB for 1 USD. Smaller means cheaper.',
	)
	enabled = models.BooleanField(default=True)
	last_fetch_at = models.DateTimeField(null=True, blank=True)
	last_fetch_status = models.CharField(
		max_length=16,
		choices=FetchStatus.choices,
		default=FetchStatus.NEVER,
	)
	last_error = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True, db_index=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['name', 'base_url']
		constraints = [
			models.UniqueConstraint(fields=['owner', 'base_url'], name='collector_site_owner_base_url_unique'),
		]

	def __str__(self) -> str:
		return self.name or self.base_url

	def clean(self):
		super().clean()
		self.base_url = normalize_base_url(self.base_url)
		duplicate = CompetitorSite.objects.filter(owner=self.owner, base_url=self.base_url)
		if self.pk:
			duplicate = duplicate.exclude(pk=self.pk)
		if duplicate.exists():
			raise ValidationError({'base_url': 'This site already exists in the current account.'})
		if self.usd_exchange_rate is not None and self.usd_exchange_rate <= 0:
			raise ValidationError({'usd_exchange_rate': 'USD exchange rate must be greater than 0.'})

	def save(self, *args, **kwargs):
		self.full_clean()
		super().save(*args, **kwargs)


class FetchRun(models.Model):
	class Status(models.TextChoices):
		RUNNING = 'running', 'Running'
		SUCCESS = 'success', 'Success'
		FAILED = 'failed', 'Failed'

	site = models.ForeignKey(CompetitorSite, on_delete=models.CASCADE, related_name='fetch_runs')
	requested_url = models.URLField(max_length=500, blank=True)
	started_at = models.DateTimeField(default=timezone.now)
	finished_at = models.DateTimeField(null=True, blank=True)
	status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING)
	error_message = models.TextField(blank=True)
	http_status_code = models.PositiveIntegerField(null=True, blank=True)
	response_excerpt = models.TextField(blank=True)
	created_count = models.PositiveIntegerField(default=0)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['-started_at']

	def __str__(self) -> str:
		return f'{self.site} @ {self.started_at:%Y-%m-%d %H:%M:%S}'


class ModelPriceSnapshot(models.Model):
	class QuotaType(models.IntegerChoices):
		TOKEN = 0, 'Token'
		REQUEST = 1, 'Request'

	fetch_run = models.ForeignKey(FetchRun, on_delete=models.CASCADE, related_name='snapshots')
	site = models.ForeignKey(CompetitorSite, on_delete=models.CASCADE, related_name='snapshots')
	model_name = models.CharField(max_length=255)
	normalized_model_name = models.CharField(max_length=255, db_index=True)
	vendor_name = models.CharField(max_length=120, blank=True, db_index=True)
	quota_type = models.PositiveSmallIntegerField(choices=QuotaType.choices)
	input_price_usd_per_1m = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
	output_price_usd_per_1m = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
	request_price_usd = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
	input_price_converted_per_1m = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
	output_price_converted_per_1m = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
	request_price_converted = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
	raw_model_ratio = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
	raw_completion_ratio = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
	raw_model_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
	raw_cache_ratio = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
	raw_create_cache_ratio = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
	billing_mode = models.CharField(max_length=64, blank=True)
	billing_expr = models.TextField(blank=True)
	supported_endpoint_types_json = models.TextField(blank=True, default='[]')
	raw_enable_groups_json = models.TextField(blank=True)
	snapshot_at = models.DateTimeField(default=timezone.now)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['-snapshot_at', 'normalized_model_name']
		indexes = [
			models.Index(fields=['normalized_model_name']),
			models.Index(fields=['site', 'normalized_model_name']),
			models.Index(fields=['fetch_run']),
		]

	def __str__(self) -> str:
		return f'{self.model_name} @ {self.site}'

	def save(self, *args, **kwargs):
		self.normalized_model_name = normalize_model_name(self.model_name)
		super().save(*args, **kwargs)

	@property
	def is_dynamic(self) -> bool:
		return bool((self.billing_mode or '').strip() or (self.billing_expr or '').strip())

	@property
	def supported_endpoint_types(self):
		try:
			value = json.loads(self.supported_endpoint_types_json or '[]')
			return value if isinstance(value, list) else []
		except (TypeError, ValueError, json.JSONDecodeError):
			return []

	@property
	def raw_enable_groups(self):
		try:
			value = json.loads(self.raw_enable_groups_json or '[]')
			return value if isinstance(value, list) else []
		except (TypeError, ValueError, json.JSONDecodeError):
			return []


class NormalizationSettings(models.Model):
	class RankingMode(models.TextChoices):
		INPUT_OUTPUT = 'input_output', 'Input and output'
		INPUT_ONLY = 'input_only', 'Input only'
		OUTPUT_ONLY = 'output_only', 'Output only'
		DISPLAY_ONLY = 'display_only', 'Display only'

	default_usd_exchange_rate = models.DecimalField(max_digits=12, decimal_places=6, default=Decimal('7.20'))
	ranking_mode = models.CharField(max_length=32, choices=RankingMode.choices, default=RankingMode.INPUT_OUTPUT)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		verbose_name_plural = 'Normalization settings'

	@classmethod
	def current(cls):
		settings_row, _created = cls.objects.get_or_create(pk=1)
		return settings_row

	def clean(self):
		super().clean()
		if self.default_usd_exchange_rate <= 0:
			raise ValidationError({'default_usd_exchange_rate': 'Default USD exchange rate must be greater than 0.'})

	def save(self, *args, **kwargs):
		self.pk = 1
		self.full_clean()
		super().save(*args, **kwargs)

	def __str__(self) -> str:
		return 'Normalization settings'


class ModelAlias(models.Model):
	source_model_name = models.CharField(max_length=255, unique=True)
	target_model_name = models.CharField(max_length=255)
	note = models.TextField(blank=True)
	enabled = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['source_model_name']

	@classmethod
	def resolve(cls, normalized_model_name: str) -> str:
		raw_name = (normalized_model_name or '').strip()
		if not raw_name:
			return ''
		alias = cls.objects.filter(source_model_name=raw_name, enabled=True).only('target_model_name').first()
		return alias.target_model_name if alias else raw_name

	def clean(self):
		super().clean()
		self.source_model_name = normalize_model_name(self.source_model_name)
		self.target_model_name = normalize_model_name(self.target_model_name)
		if not self.source_model_name or not self.target_model_name:
			raise ValidationError('Alias source and target are required.')

	def save(self, *args, **kwargs):
		self.full_clean()
		super().save(*args, **kwargs)

	def __str__(self) -> str:
		return f'{self.source_model_name} -> {self.target_model_name}'


class LoginCode(models.Model):
	email = models.EmailField(db_index=True)
	code_hash = models.CharField(max_length=128)
	request_ip = models.GenericIPAddressField(null=True, blank=True)
	expires_at = models.DateTimeField(db_index=True)
	attempt_count = models.PositiveSmallIntegerField(default=0)
	used_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True, db_index=True)

	class Meta:
		ordering = ['-created_at']
		indexes = [
			models.Index(fields=['email', 'expires_at']),
		]

	def __str__(self) -> str:
		return f'{self.email} @ {self.created_at:%Y-%m-%d %H:%M:%S}'

	@classmethod
	def create_for_email(cls, email: str, code: str, request_ip: str = ''):
		ttl_seconds = getattr(settings, 'ARGUS_LOGIN_CODE_TTL_SECONDS', 600)
		return cls.objects.create(
			email=email,
			code_hash=make_password(code),
			request_ip=request_ip or None,
			expires_at=timezone.now() + timedelta(seconds=ttl_seconds),
		)

	@classmethod
	def purge_stale(cls):
		retention_seconds = getattr(settings, 'ARGUS_LOGIN_CODE_RETENTION_SECONDS', 60 * 60 * 24 * 30)
		cutoff = timezone.now() - timedelta(seconds=retention_seconds)
		deleted_count, _ = cls.objects.filter(created_at__lt=cutoff).delete()
		return deleted_count

	@property
	def is_expired(self) -> bool:
		return timezone.now() >= self.expires_at

	@property
	def is_used(self) -> bool:
		return self.used_at is not None

	def verify(self, code: str) -> bool:
		max_attempts = getattr(settings, 'ARGUS_LOGIN_CODE_MAX_ATTEMPTS', 5)
		if self.is_used or self.is_expired or self.attempt_count >= max_attempts:
			return False
		return check_password(code, self.code_hash)

	def register_failed_attempt(self):
		self.attempt_count += 1
		self.save(update_fields=['attempt_count'])

	def mark_used(self):
		self.used_at = timezone.now()
		self.save(update_fields=['used_at'])


class UserSessionState(models.Model):
	user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='argus_session_state')
	active_session_key = models.CharField(max_length=128, blank=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self) -> str:
		return self.user.get_username()


class UserPlanSubscription(models.Model):
	class Status(models.TextChoices):
		ACTIVE = 'active', 'Active'
		EXPIRED = 'expired', 'Expired'
		CANCELED = 'canceled', 'Canceled'

	user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='argus_plan_subscription')
	plan_code = models.CharField(max_length=32, default='free')
	status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
	starts_at = models.DateTimeField(default=timezone.now)
	expires_at = models.DateTimeField(null=True, blank=True)
	auto_renew = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['user_id']

	def __str__(self) -> str:
		return f'{self.user.get_username()} · {self.plan_code}'

	@property
	def is_active(self) -> bool:
		if self.status != self.Status.ACTIVE:
			return False
		return self.expires_at is None or self.expires_at > timezone.now()


class PaymentOrder(models.Model):
	class Status(models.TextChoices):
		PENDING = 'pending', 'Pending'
		PAID = 'paid', 'Paid'
		FAILED = 'failed', 'Failed'
		CANCELED = 'canceled', 'Canceled'

	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='argus_payment_orders')
	trade_no = models.CharField(max_length=64, unique=True)
	provider = models.CharField(max_length=32, default='epay')
	payment_method = models.CharField(max_length=32, blank=True)
	plan_code = models.CharField(max_length=32)
	billing_cycle = models.CharField(max_length=32)
	amount_rmb = models.DecimalField(max_digits=10, decimal_places=2)
	status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
	provider_payload_json = models.TextField(blank=True, default='{}')
	paid_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-created_at']

	def __str__(self) -> str:
		return self.trade_no
