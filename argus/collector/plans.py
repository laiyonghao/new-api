from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Plan:
	code: str
	label: str
	site_limit: int
	compare_limit: int
	auto_runs_per_day: int
	manual_cooldown_minutes: int
	digest_enabled: bool
	price_label: str


PLANS = {
	'free': Plan(
		code='free',
		label='Free',
		site_limit=2,
		compare_limit=3,
		auto_runs_per_day=1,
		manual_cooldown_minutes=60,
		digest_enabled=False,
		price_label='¥0',
	),
	'pro': Plan(
		code='pro',
		label='Pro',
		site_limit=10,
		compare_limit=3,
		auto_runs_per_day=3,
		manual_cooldown_minutes=60,
		digest_enabled=True,
		price_label='¥50/季 · ¥100/年',
	),
	'plus': Plan(
		code='plus',
		label='Plus',
		site_limit=50,
		compare_limit=5,
		auto_runs_per_day=3,
		manual_cooldown_minutes=60,
		digest_enabled=True,
		price_label='¥50/月 · ¥300/年',
	),
	'max': Plan(
		code='max',
		label='Max',
		site_limit=300,
		compare_limit=5,
		auto_runs_per_day=3,
		manual_cooldown_minutes=60,
		digest_enabled=True,
		price_label='¥1000/年',
	),
}

DEFAULT_PLAN_CODE = 'free'

PLAN_PRICES = {
	('pro', 'quarter'): Decimal('50.00'),
	('pro', 'year'): Decimal('100.00'),
	('plus', 'month'): Decimal('50.00'),
	('plus', 'year'): Decimal('300.00'),
	('max', 'year'): Decimal('1000.00'),
}


def get_plan(code):
	return PLANS.get((code or '').strip().lower(), PLANS[DEFAULT_PLAN_CODE])


def get_plan_price(plan_code, billing_cycle):
	return PLAN_PRICES.get(((plan_code or '').strip().lower(), (billing_cycle or '').strip().lower()))


def site_usage_percent(site_count, plan):
	if plan.site_limit <= 0:
		return Decimal('0')
	return min(Decimal('100'), (Decimal(site_count) / Decimal(plan.site_limit) * Decimal('100')).quantize(Decimal('1')))
