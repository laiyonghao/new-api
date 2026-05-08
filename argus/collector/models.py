from decimal import Decimal
import re
import json
from urllib.parse import urlparse

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

	base_url = models.URLField(unique=True, max_length=255)
	name = models.CharField(max_length=120, blank=True)
	note = models.TextField(blank=True)
	icon_url = models.URLField(max_length=500, blank=True)
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
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['name', 'base_url']

	def __str__(self) -> str:
		return self.name or self.base_url

	def clean(self):
		super().clean()
		self.base_url = normalize_base_url(self.base_url)
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
