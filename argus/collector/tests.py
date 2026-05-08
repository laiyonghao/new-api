from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import CompetitorSite, FetchRun, ModelPriceSnapshot


class ComparisonPageTests(TestCase):
	def test_comparison_page_lists_cheapest_site_for_each_model(self):
		north = CompetitorSite.objects.create(base_url='https://north.example.com', name='North Relay')
		quiet = CompetitorSite.objects.create(base_url='https://quiet.example.com', name='Quiet Gateway')
		north_run = FetchRun.objects.create(site=north, status=FetchRun.Status.SUCCESS, finished_at=timezone.now())
		quiet_run = FetchRun.objects.create(site=quiet, status=FetchRun.Status.SUCCESS, finished_at=timezone.now())

		ModelPriceSnapshot.objects.create(
			fetch_run=north_run,
			site=north,
			model_name='claude-sonnet-4-6-20260501',
			vendor_name='Anthropic',
			quota_type=ModelPriceSnapshot.QuotaType.TOKEN,
			input_price_converted_per_1m=Decimal('8.50'),
			output_price_converted_per_1m=Decimal('40.00'),
		)
		ModelPriceSnapshot.objects.create(
			fetch_run=quiet_run,
			site=quiet,
			model_name='claude-sonnet-4-6-20260501',
			vendor_name='Anthropic',
			quota_type=ModelPriceSnapshot.QuotaType.TOKEN,
			input_price_converted_per_1m=Decimal('7.90'),
			output_price_converted_per_1m=Decimal('42.00'),
		)
		ModelPriceSnapshot.objects.create(
			fetch_run=quiet_run,
			site=quiet,
			model_name='mj-chat',
			vendor_name='Midjourney',
			quota_type=ModelPriceSnapshot.QuotaType.REQUEST,
			request_price_converted=Decimal('0.12'),
		)

		response = self.client.get(reverse('comparison'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'claude-sonnet-4-6')
		self.assertContains(response, 'mj-chat')
		self.assertContains(response, 'Quiet Gateway')
		self.assertContains(response, 'North Relay')
		self.assertContains(response, '2 个可精确排名模型')
