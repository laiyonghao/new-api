import hashlib
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlparse
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import CompetitorSite, FetchRun, LoginCode, ModelAlias, ModelPriceSnapshot, NormalizationSettings, PaymentOrder, UserPlanSubscription, UserSessionState
from .services.comparison import build_comparison_rows


class ComparisonPageTests(TestCase):
	def _create_token_price_pair(self):
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
		return north, quiet

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

	def test_comparison_rows_respect_input_only_ranking_mode(self):
		_north, quiet = self._create_token_price_pair()

		rows = build_comparison_rows(ranking_mode=NormalizationSettings.RankingMode.INPUT_ONLY)

		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]['input_site'], quiet)
		self.assertIsNone(rows[0]['output_site'])

	def test_comparison_rows_respect_output_only_ranking_mode(self):
		north, _quiet = self._create_token_price_pair()

		rows = build_comparison_rows(ranking_mode=NormalizationSettings.RankingMode.OUTPUT_ONLY)

		self.assertEqual(len(rows), 1)
		self.assertIsNone(rows[0]['input_site'])
		self.assertEqual(rows[0]['output_site'], north)

	def test_display_only_ranking_mode_excludes_token_price_ranking(self):
		self._create_token_price_pair()

		rows = build_comparison_rows(ranking_mode=NormalizationSettings.RankingMode.DISPLAY_ONLY)

		self.assertEqual(rows, [])

	def test_display_only_ranking_mode_still_ranks_request_models(self):
		request_site = CompetitorSite.objects.create(base_url='https://request.example.com', name='Request Relay')
		request_run = FetchRun.objects.create(site=request_site, status=FetchRun.Status.SUCCESS, finished_at=timezone.now())
		ModelPriceSnapshot.objects.create(
			fetch_run=request_run,
			site=request_site,
			model_name='mj-chat',
			vendor_name='Midjourney',
			quota_type=ModelPriceSnapshot.QuotaType.REQUEST,
			request_price_converted=Decimal('0.12'),
		)

		rows = build_comparison_rows(ranking_mode=NormalizationSettings.RankingMode.DISPLAY_ONLY)

		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]['request_site'], request_site)


class AdminSiteManagementTests(TestCase):
	def setUp(self):
		User = get_user_model()
		self.admin_user = User.objects.create_superuser(username='admin-user', email='admin@example.com', password='secret')
		self.client.force_login(self.admin_user)

	def test_competitor_site_changelist_exposes_management_columns(self):
		site = CompetitorSite.objects.create(
			base_url='https://admin.example.com',
			name='Admin Relay',
			owner=self.admin_user,
			system_version='v2.0.0',
			system_start_time=1777561625,
		)
		fetch_run = FetchRun.objects.create(site=site, status=FetchRun.Status.SUCCESS, finished_at=timezone.now(), created_count=2)
		ModelPriceSnapshot.objects.create(
			fetch_run=fetch_run,
			site=site,
			model_name='admin-model',
			quota_type=ModelPriceSnapshot.QuotaType.REQUEST,
		)

		response = self.client.get(reverse('admin:collector_competitorsite_changelist'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Admin Relay')
		self.assertContains(response, 'admin@example.com')
		self.assertContains(response, 'v2.0.0')
		self.assertContains(response, 'Refresh status')
		self.assertContains(response, 'Collect')
		self.assertContains(response, 'Cheapest Comparison')

	def test_all_collector_models_are_registered_in_admin(self):
		from django.contrib import admin

		for model in [
			CompetitorSite,
			FetchRun,
			ModelPriceSnapshot,
			ModelAlias,
			NormalizationSettings,
			LoginCode,
			UserSessionState,
			UserPlanSubscription,
			PaymentOrder,
		]:
			with self.subTest(model=model.__name__):
				self.assertIn(model, admin.site._registry)

	def test_refresh_status_admin_view_updates_remote_metadata(self):
		site = CompetitorSite.objects.create(base_url='https://refresh.example.com', name='', usd_exchange_rate=Decimal('7.200000'))
		metadata = {
			'name': 'Remote Refresh',
			'icon_url': 'https://refresh.example.com/logo.png',
			'system_start_time': 1777561625,
			'system_version': 'v3.1.4',
			'usd_exchange_rate': Decimal('1.25'),
		}

		with patch('collector.admin.discover_site_status_metadata', return_value=metadata) as discover:
			response = self.client.get(reverse('admin:collector_competitorsite_refresh_status', args=[site.id]))

		self.assertEqual(response.status_code, 302)
		discover.assert_called_once()
		site.refresh_from_db()
		self.assertEqual(site.name, 'Remote Refresh')
		self.assertEqual(site.icon_url, 'https://refresh.example.com/logo.png')
		self.assertEqual(site.system_start_time, 1777561625)
		self.assertEqual(site.system_version, 'v3.1.4')
		self.assertEqual(site.usd_exchange_rate, Decimal('1.250000'))

	def test_collect_site_admin_view_collects_one_site(self):
		site = CompetitorSite.objects.create(base_url='https://collect.example.com', name='Collect Relay')
		fetch_status = SimpleNamespace(status=FetchRun.Status.SUCCESS, created_count=4, error_message='')

		with patch('collector.admin.collect_site_pricing', return_value=fetch_status) as collect:
			response = self.client.get(reverse('admin:collector_competitorsite_collect_one', args=[site.id]))

		self.assertEqual(response.status_code, 302)
		collect.assert_called_once_with(site)


class AppPageTests(TestCase):
	def setUp(self):
		cache.clear()
		User = get_user_model()
		self.user = User.objects.create_user(username='app-page-user', email='app-page@example.com')
		self.client.force_login(self.user)

	def _mock_site_save_collection(self, metadata=None, fetch_status=None):
		metadata = metadata if metadata is not None else {
			'name': 'Status Relay',
			'icon_url': 'https://status.example.com/logo.png',
			'system_start_time': 1777561625,
			'system_version': 'v1.2.3',
			'usd_exchange_rate': Decimal('1.00'),
		}
		fetch_status = fetch_status or SimpleNamespace(status=FetchRun.Status.SUCCESS, created_count=3, error_message='')
		return patch('collector.views.discover_site_status_metadata', return_value=metadata), patch('collector.views.collect_site_pricing', return_value=fetch_status)

	def test_home_uses_app_template(self):
		response = self.client.get(reverse('home'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'AI中转站')
		self.assertContains(response, 'data-login-send-url')
		self.assertContains(response, 'id="watchlist-url"')
		self.assertContains(response, f'action="{reverse("home_site_submit")}"')
		self.assertContains(response, 'name="base_url"')
		self.assertContains(response, 'data-home-watchlist-form')
		self.assertContains(response, 'data-home-watchlist-url')
		self.assertContains(response, 'data-home-watchlist-spinner')
		self.assertContains(response, 'data-home-watchlist-label')
		self.assertContains(response, '>加入 Watchlist</span>', count=1)
		self.assertContains(response, 'placeholder="输入中转站网址，例如 https://example.ai"')
		self.assertContains(response, '输入候选站点网址，开始持续追踪模型价格、倍率规则和采集状态。')
		self.assertNotContains(response, 'AI Relay Price Ops')
		self.assertNotContains(response, '>开始使用</a>')
		self.assertNotContains(response, '>打开 Watchlist</a>')
		self.assertNotContains(response, '监控站点')
		self.assertNotContains(response, '模型快照')
		self.assertNotContains(response, '今日巡价')
		self.assertNotContains(response, 'https://north.example.ai')

	def test_home_submit_creates_site_for_authenticated_user(self):
		status_mock, pricing_mock = self._mock_site_save_collection(metadata={
			'name': 'Homepage Relay',
			'icon_url': 'https://homepage.example.com/logo.png',
			'system_start_time': 1777561625,
			'system_version': 'v9.0.0',
			'usd_exchange_rate': Decimal('1.50'),
		})
		with status_mock as discover, pricing_mock as collect:
			response = self.client.post(reverse('home_site_submit'), {'base_url': 'homepage.example.com'})

		self.assertRedirects(response, reverse('watchlist_sites'))
		site = CompetitorSite.objects.get(base_url='https://homepage.example.com')
		self.assertEqual(site.owner, self.user)
		self.assertEqual(site.name, 'Homepage Relay')
		self.assertEqual(site.system_version, 'v9.0.0')
		self.assertEqual(site.usd_exchange_rate, Decimal('1.500000'))
		discover.assert_called_once()
		collect.assert_called_once_with(site)

	def test_home_submit_previews_site_for_anonymous_user_without_saving(self):
		self.client.logout()
		preview_snapshot = ModelPriceSnapshot(
			model_name='gpt-preview-20260509',
			normalized_model_name='gpt-preview',
			vendor_name='OpenAI',
			quota_type=ModelPriceSnapshot.QuotaType.TOKEN,
			input_price_converted_per_1m=Decimal('2.00'),
			output_price_converted_per_1m=Decimal('6.00'),
		)
		metadata = {
			'name': 'Preview Relay',
			'icon_url': 'https://preview.example.com/logo.png',
			'system_start_time': 1777561625,
			'system_version': 'v1.0.0',
			'usd_exchange_rate': Decimal('1.25'),
		}
		preview = SimpleNamespace(status=FetchRun.Status.SUCCESS, created_count=1, error_message='', snapshots=[preview_snapshot])

		with patch('collector.views.discover_site_status_metadata', return_value=metadata) as discover, patch('collector.views.preview_site_pricing', return_value=preview) as preview_pricing:
			response = self.client.post(reverse('home_site_submit'), {'base_url': 'preview.example.com'})

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, '这个站点可以被 CheapToken')
		self.assertContains(response, '比价')
		self.assertContains(response, '已完成数据采集')
		self.assertContains(response, 'Preview Relay')
		self.assertContains(response, 'gpt-preview')
		self.assertContains(response, '注册/登入并保存')
		self.assertEqual(CompetitorSite.objects.count(), 0)
		self.assertEqual(FetchRun.objects.count(), 0)
		self.assertEqual(ModelPriceSnapshot.objects.count(), 0)
		discover.assert_called_once()
		preview_pricing.assert_called_once()

	def test_navigation_uses_current_user_plan(self):
		User = get_user_model()
		user = User.objects.create_user(username='nav-plus', email='nav-plus@example.com')
		UserPlanSubscription.objects.create(user=user, plan_code='plus')
		self.client.force_login(user)

		response = self.client.get(reverse('home'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'nav-plus@example.com')
		self.assertContains(response, 'nav-plus@example.com · Plus')
		self.assertNotContains(response, 'nav-plus@example.com · Pro')

	def test_anonymous_navigation_uses_register_login_button(self):
		self.client.logout()
		response = self.client.get(reverse('pricing_billing'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, '注册/登入')
		self.assertNotContains(response, '未登录 · Free')
		self.assertNotContains(response, 'argus-avatar')

	def test_footer_links_to_cheaptoken_domain(self):
		self.client.logout()
		response = self.client.get(reverse('home'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'href="https://cheaptoken.io/" target="_blank" rel="noopener noreferrer">cheaptoken.io</a>')
		self.assertNotContains(response, 'href="/account/account.html">账户</a>')

	def test_watchlist_sites_page_renders_database_sites(self):
		User = get_user_model()
		user = User.objects.create_user(username='watch-user', email='watch@example.com')
		self.client.force_login(user)
		CompetitorSite.objects.create(
			owner=user,
			base_url='https://north.example.com',
			name='North Relay',
			note='真实数据驱动',
		)

		response = self.client.get(reverse('watchlist_sites'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'North Relay')
		self.assertContains(response, '真实数据驱动')
		self.assertContains(response, 'data-site-save-url')

	def test_anonymous_users_cannot_access_watchlist_or_account_pages(self):
		self.client.logout()
		protected_urls = [
			reverse('watchlist_sites'),
			reverse('watchlist_comparison'),
			reverse('watchlist_custom_comparison'),
			reverse('watchlist_fetch_runs'),
			reverse('watchlist_rules'),
			reverse('account'),
		]

		for url in protected_urls:
			with self.subTest(url=url):
				response = self.client.get(url)
				self.assertEqual(response.status_code, 302)
				self.assertEqual(response.headers['Location'], f'{reverse("login")}?{urlencode({"next": url})}')

	def test_login_page_matches_dialog_flow_and_preserves_next(self):
		self.client.logout()
		response = self.client.get(reverse('login'), {'next': reverse('watchlist_rules')})

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, '注册/登入')
		self.assertContains(response, 'data-login-form')
		self.assertContains(response, 'data-login-email-input')
		self.assertContains(response, 'data-login-code-input')
		self.assertContains(response, f'href="{reverse("watchlist_rules")}"')
		self.assertNotContains(response, 'data-login-success')
		self.assertNotContains(response, '邮箱验证通过，当前会话已恢复。')
		self.assertNotContains(response, 'value="hello@example.com"')
		self.assertNotContains(response, 'value="1024"')

	def test_login_page_rejects_external_next(self):
		self.client.logout()
		response = self.client.get(reverse('login'), {'next': 'https://example.com/phish'})

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, f'href="{reverse("watchlist_sites")}"')
		self.assertNotContains(response, 'https://example.com/phish')

	def test_anonymous_users_cannot_call_watchlist_mutations(self):
		self.client.logout()
		for url in [reverse('site_save'), reverse('site_deactivate'), reverse('site_fetch'), reverse('rules_save')]:
			with self.subTest(url=url):
				response = self.client.post(url, {})
				self.assertEqual(response.status_code, 401)

	def test_watchlist_tool_pages_use_mobile_collapses(self):
		for route_name in [
			'watchlist_sites',
			'watchlist_comparison',
			'watchlist_custom_comparison',
			'watchlist_fetch_runs',
			'watchlist_rules',
		]:
			with self.subTest(route_name=route_name):
				response = self.client.get(reverse(route_name))

				self.assertEqual(response.status_code, 200)
				self.assertContains(response, 'class="argus-shell argus-tool-page')
				self.assertContains(response, 'data-mobile-collapse')

	def test_site_form_url_redirects_to_site_directory(self):
		response = self.client.get(reverse('watchlist_site_form'))

		self.assertRedirects(response, reverse('watchlist_sites'))

	def test_watchlist_comparison_page_uses_database_snapshots(self):
		north = CompetitorSite.objects.create(owner=self.user, base_url='https://north.example.com', name='North Relay')
		quiet = CompetitorSite.objects.create(owner=self.user, base_url='https://quiet.example.com', name='Quiet Gateway')
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

		response = self.client.get(reverse('watchlist_comparison'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'claude-sonnet-4-6')
		self.assertContains(response, 'Quiet Gateway')
		self.assertContains(response, 'North Relay')
		self.assertContains(response, '<span data-comparison-visible-count>1</span>/<span data-comparison-total-count>1</span>')
		self.assertNotContains(response, '站点筛选')
		self.assertNotContains(response, 'data-comparison-site-select')
		self.assertNotContains(response, 'data-comparison-sites="')
		self.assertContains(response, '模型、计费、供应商')
		self.assertNotContains(response, 'aria-label="结果摘要"')
		self.assertNotContains(response, '比较口径')
		self.assertContains(response, 'data-comparison-filter')
		self.assertContains(response, 'data-mobile-collapse')
		self.assertContains(response, 'data-comparison-row')
		self.assertNotContains(response, '筛选比价')
		self.assertNotContains(response, 'argus-compare-cell-best')

		filtered_response = self.client.get(reverse('watchlist_comparison'), {'normalized_model_name': 'missing-model'})

		self.assertEqual(filtered_response.status_code, 200)
		self.assertContains(filtered_response, 'claude-sonnet-4-6')
		self.assertContains(filtered_response, 'value="missing-model"')

	def test_custom_comparison_page_filters_database_snapshots(self):
		site = CompetitorSite.objects.create(owner=self.user, base_url='https://custom.example.com', name='Custom Relay')
		fetch_run = FetchRun.objects.create(site=site, status=FetchRun.Status.SUCCESS, finished_at=timezone.now())
		ModelPriceSnapshot.objects.create(
			fetch_run=fetch_run,
			site=site,
			model_name='gpt-5-3-codex',
			vendor_name='OpenAI',
			quota_type=ModelPriceSnapshot.QuotaType.TOKEN,
			input_price_converted_per_1m=Decimal('3.75'),
			output_price_converted_per_1m=Decimal('3.75'),
		)

		response = self.client.get(reverse('watchlist_custom_comparison'), {'normalized_model_name': 'codex'})

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'gpt-5-3-codex')
		self.assertContains(response, 'Custom Relay')
		self.assertContains(response, 'value="codex"')

	def test_save_site_creates_competitor_site(self):
		status_mock, pricing_mock = self._mock_site_save_collection(metadata={
			'name': 'Status Bridge',
			'icon_url': 'https://south.example.com/logo.png',
			'system_start_time': 1777561625,
			'system_version': 'v1.2.3',
			'usd_exchange_rate': Decimal('1.25'),
		})
		with status_mock as discover, pricing_mock as collect:
			response = self.client.post(reverse('site_save'), {
				'base_url': 'south.example.com',
				'name': '',
				'note': '新增站点',
				'usd_exchange_rate': '7.12',
				'enabled': '0',
			})

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.json()['ok'])
		site = CompetitorSite.objects.get(name='Status Bridge')
		self.assertEqual(site.base_url, 'https://south.example.com')
		self.assertEqual(site.note, '')
		self.assertTrue(site.enabled)
		self.assertEqual(site.icon_url, 'https://south.example.com/logo.png')
		self.assertEqual(site.system_start_time, 1777561625)
		self.assertEqual(site.system_version, 'v1.2.3')
		self.assertEqual(site.usd_exchange_rate, Decimal('1.250000'))
		discover.assert_called_once()
		collect.assert_called_once_with(site)

	def test_deactivate_site_keeps_snapshots(self):
		site = CompetitorSite.objects.create(owner=self.user, base_url='https://archive.example.com', name='Archive Hub')
		fetch_run = FetchRun.objects.create(site=site, status=FetchRun.Status.SUCCESS, finished_at=timezone.now())
		ModelPriceSnapshot.objects.create(
			fetch_run=fetch_run,
			site=site,
			model_name='claude-test',
			quota_type=ModelPriceSnapshot.QuotaType.TOKEN,
		)

		response = self.client.post(reverse('site_deactivate'), {'site_id': site.id})

		self.assertEqual(response.status_code, 200)
		site.refresh_from_db()
		self.assertFalse(site.enabled)
		self.assertEqual(ModelPriceSnapshot.objects.filter(site=site).count(), 1)

	def test_fetch_site_rejects_disabled_site(self):
		site = CompetitorSite.objects.create(owner=self.user, base_url='https://disabled.example.com', name='Disabled', enabled=False)

		response = self.client.post(reverse('site_fetch'), {'site_id': site.id})

		self.assertEqual(response.status_code, 400)
		self.assertFalse(response.json()['ok'])

	@override_settings(ARGUS_MANUAL_FETCH_COOLDOWN_SECONDS=3600)
	def test_fetch_site_respects_manual_cooldown(self):
		site = CompetitorSite.objects.create(owner=self.user, base_url='https://cooldown.example.com', name='Cooldown')
		FetchRun.objects.create(site=site, status=FetchRun.Status.SUCCESS, started_at=timezone.now(), finished_at=timezone.now())

		response = self.client.post(reverse('site_fetch'), {'site_id': site.id})

		self.assertEqual(response.status_code, 429)
		self.assertFalse(response.json()['ok'])
		self.assertIn('手动采集过于频繁', response.json()['message'])

	@override_settings(ARGUS_MANUAL_FETCH_COOLDOWN_SECONDS=3600)
	def test_watchlist_sites_page_disables_manual_fetch_during_cooldown(self):
		site = CompetitorSite.objects.create(owner=self.user, base_url='https://cooldown-ui.example.com', name='Cooldown UI')
		FetchRun.objects.create(site=site, status=FetchRun.Status.SUCCESS, started_at=timezone.now(), finished_at=timezone.now())

		response = self.client.get(reverse('watchlist_sites'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, '60 分钟后可采集')
		self.assertContains(response, '冷却中')
		self.assertContains(response, 'disabled title="60 分钟后可采集"')

	@override_settings(ARGUS_MANUAL_FETCH_COOLDOWN_SECONDS=3600)
	def test_watchlist_sites_page_allows_manual_fetch_after_cooldown(self):
		site = CompetitorSite.objects.create(owner=self.user, base_url='https://ready-ui.example.com', name='Ready UI')
		started_at = timezone.now() - timedelta(hours=2)
		FetchRun.objects.create(site=site, status=FetchRun.Status.SUCCESS, started_at=started_at, finished_at=started_at)

		response = self.client.get(reverse('watchlist_sites'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, '可立即执行')
		self.assertContains(response, f'data-site-id="{site.id}" type="button" >采集</button>')

	def test_account_page_renders_user_plan_and_capacity(self):
		User = get_user_model()
		user = User.objects.create_user(username='plan-user', email='plan@example.com')
		UserPlanSubscription.objects.create(user=user, plan_code='plus')
		CompetitorSite.objects.create(owner=user, base_url='https://one.example.com', name='One')
		CompetitorSite.objects.create(owner=user, base_url='https://two.example.com', name='Two')
		self.client.force_login(user)

		response = self.client.get(reverse('account'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'plan@example.com')
		self.assertContains(response, 'Plus')
		self.assertContains(response, '2/50')

	def test_account_page_shows_free_plan_without_daily_digest(self):
		User = get_user_model()
		user = User.objects.create_user(username='free-digest-user', email='free-digest@example.com')
		self.client.force_login(user)

		response = self.client.get(reverse('account'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Free')
		self.assertContains(response, '08:00 早报')
		self.assertContains(response, '未开启')
		self.assertContains(response, '当前套餐不含')
		self.assertNotContains(response, '明早发送')

	def test_free_plan_prevents_creating_site_over_limit(self):
		User = get_user_model()
		user = User.objects.create_user(username='free-user', email='free@example.com')
		self.client.force_login(user)
		CompetitorSite.objects.create(owner=user, base_url='https://one.example.com', name='One')
		CompetitorSite.objects.create(owner=user, base_url='https://two.example.com', name='Two')

		response = self.client.post(reverse('site_save'), {
			'base_url': 'three.example.com',
			'name': 'Three',
			'enabled': '1',
		})

		self.assertEqual(response.status_code, 400)
		self.assertFalse(CompetitorSite.objects.filter(name='Three').exists())
		self.assertIn('Free 套餐最多可启用 2 个站点', response.json()['message'])

	def test_site_directory_is_scoped_to_current_user(self):
		User = get_user_model()
		current_user = User.objects.create_user(username='current-user', email='current@example.com')
		other_user = User.objects.create_user(username='other-user', email='other@example.com')
		CompetitorSite.objects.create(owner=current_user, base_url='https://mine.example.com', name='Mine')
		CompetitorSite.objects.create(owner=other_user, base_url='https://other.example.com', name='Other')
		self.client.force_login(current_user)

		response = self.client.get(reverse('watchlist_sites'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Mine')
		self.assertNotContains(response, 'Other')

	def test_save_site_assigns_current_user_as_owner(self):
		User = get_user_model()
		user = User.objects.create_user(username='owner-user', email='owner@example.com')
		self.client.force_login(user)

		status_mock, pricing_mock = self._mock_site_save_collection()
		with status_mock, pricing_mock:
			response = self.client.post(reverse('site_save'), {
				'base_url': 'owned.example.com',
				'name': 'Owned Site',
			})

		self.assertEqual(response.status_code, 200)
		self.assertEqual(CompetitorSite.objects.get(name='Owned Site').owner, user)

	def test_save_site_ignores_note_and_enabled_edits(self):
		site = CompetitorSite.objects.create(
			owner=self.user,
			base_url='https://existing.example.com',
			name='Existing',
			note='内部保留',
			enabled=True,
			usd_exchange_rate=Decimal('7.200000'),
		)
		status_mock, pricing_mock = self._mock_site_save_collection(metadata={
			'name': 'Remote Existing',
			'icon_url': '',
			'system_start_time': None,
			'system_version': '',
			'usd_exchange_rate': None,
		})
		with status_mock, pricing_mock:
			response = self.client.post(reverse('site_save'), {
				'site_id': site.id,
				'base_url': 'existing.example.com',
				'name': 'Manual Existing',
				'note': '用户提交备注',
				'enabled': '0',
				'usd_exchange_rate': '',
			})

		self.assertEqual(response.status_code, 200)
		site.refresh_from_db()
		self.assertEqual(site.name, 'Manual Existing')
		self.assertEqual(site.note, '内部保留')
		self.assertTrue(site.enabled)
		self.assertEqual(site.usd_exchange_rate, Decimal('1.000000'))

	def test_user_cannot_fetch_another_users_site(self):
		User = get_user_model()
		current_user = User.objects.create_user(username='fetch-current', email='fetch-current@example.com')
		other_user = User.objects.create_user(username='fetch-other', email='fetch-other@example.com')
		other_site = CompetitorSite.objects.create(owner=other_user, base_url='https://other-fetch.example.com', name='Other Fetch')
		self.client.force_login(current_user)

		response = self.client.post(reverse('site_fetch'), {'site_id': other_site.id})

		self.assertEqual(response.status_code, 404)

	def test_single_active_session_middleware_logs_out_stale_session(self):
		User = get_user_model()
		user = User.objects.create_user(username='session-user', email='session@example.com')
		self.client.force_login(user)
		UserSessionState.objects.create(user=user, active_session_key='newer-session')

		response = self.client.get(reverse('account'))

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.headers['Location'], f'{reverse("login")}?{urlencode({"next": reverse("account")})}')
		self.assertNotIn('_auth_user_id', self.client.session)

	def test_pricing_page_sends_anonymous_users_to_login_before_checkout(self):
		self.client.logout()

		response = self.client.get(reverse('pricing_billing'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, '选择监控方案')
		self.assertContains(response, '选择 Pro')
		self.assertContains(response, 'data-authenticated="false"')
		self.assertContains(response, f'{reverse("login")}?next=')
		self.assertNotContains(response, 'data-dialog-open="checkout"')
		self.assertNotContains(response, 'data-checkout-form')

	def test_pricing_page_exposes_checkout_endpoint_for_logged_in_users(self):
		User = get_user_model()
		self.client.force_login(User.objects.create_user(username='pricing-buyer', email='pricing-buyer@example.com'))

		response = self.client.get(reverse('pricing_billing'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, '选择监控方案')
		self.assertContains(response, '选择 Pro')
		self.assertContains(response, 'data-authenticated="true"')
		self.assertNotContains(response, '查看账户')
		self.assertNotContains(response, '购买 Pro')
		self.assertContains(response, '确认订阅方案')
		self.assertContains(response, '更多')
		self.assertContains(response, '>OK</button>')
		self.assertContains(response, '支付完成后，当前账号的订阅会自动生效。')
		self.assertContains(response, '前往支付')
		self.assertNotContains(response, '订单创建前不会扣费')
		self.assertNotContains(response, '生成支付链接')
		self.assertNotContains(response, '生成 Epay 支付链接')
		self.assertNotContains(response, '打开 Epay 支付页')
		self.assertContains(response, 'data-checkout-form')
		self.assertContains(response, reverse('pricing_checkout'))

	def test_checkout_order_requires_login(self):
		self.client.logout()
		response = self.client.post(reverse('pricing_checkout'), {'plan_code': 'pro', 'billing_cycle': 'year'})

		self.assertEqual(response.status_code, 401)
		self.assertFalse(response.json()['ok'])

	def test_checkout_order_rejects_invalid_plan_cycle(self):
		User = get_user_model()
		self.client.force_login(User.objects.create_user(username='buyer', email='buyer@example.com'))

		response = self.client.post(reverse('pricing_checkout'), {'plan_code': 'free', 'billing_cycle': 'year'})

		self.assertEqual(response.status_code, 400)
		self.assertFalse(response.json()['ok'])
		self.assertEqual(PaymentOrder.objects.count(), 0)

	def test_checkout_order_creates_pending_payment_order(self):
		User = get_user_model()
		user = User.objects.create_user(username='pay-user', email='pay@example.com')
		self.client.force_login(user)

		response = self.client.post(reverse('pricing_checkout'), {
			'plan_code': 'plus',
			'billing_cycle': 'year',
			'payment_method': 'epay',
		})

		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertTrue(payload['ok'])
		order = PaymentOrder.objects.get(user=user)
		self.assertEqual(order.plan_code, 'plus')
		self.assertEqual(order.billing_cycle, 'year')
		self.assertEqual(order.amount_rmb, Decimal('300.00'))
		self.assertEqual(order.status, PaymentOrder.Status.PENDING)
		self.assertEqual(payload['order']['trade_no'], order.trade_no)

	@override_settings(
		ALLOWED_HOSTS=['testserver'],
		ARGUS_EPAY_ENABLED=True,
		ARGUS_EPAY_URL='https://pay.example.com/',
		ARGUS_EPAY_PID='1001',
		ARGUS_EPAY_KEY='secret',
	)
	def test_checkout_order_returns_signed_epay_url_when_configured(self):
		User = get_user_model()
		user = User.objects.create_user(username='epay-user', email='epay@example.com')
		self.client.force_login(user)

		response = self.client.post(reverse('pricing_checkout'), {
			'plan_code': 'pro',
			'billing_cycle': 'quarter',
			'payment_method': 'alipay',
		})

		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertTrue(payload['payment_configured'])
		payment_url = payload['payment_url']
		self.assertTrue(payment_url.startswith('https://pay.example.com/submit.php?'))
		params = parse_qs(urlparse(payment_url).query)
		order = PaymentOrder.objects.get(user=user)
		self.assertEqual(params['pid'], ['1001'])
		self.assertEqual(params['type'], ['alipay'])
		self.assertEqual(params['out_trade_no'], [order.trade_no])
		self.assertEqual(params['money'], ['50.00'])
		self.assertIn('sign', params)

	@override_settings(ARGUS_EPAY_KEY='secret')
	def test_epay_notify_marks_order_paid_and_activates_subscription(self):
		User = get_user_model()
		user = User.objects.create_user(username='paid-user', email='paid@example.com')
		order = PaymentOrder.objects.create(
			user=user,
			trade_no='ARGUS-PAID-1',
			payment_method='alipay',
			plan_code='plus',
			billing_cycle='month',
			amount_rmb=Decimal('39.00'),
		)
		payload = {
			'pid': '1001',
			'out_trade_no': order.trade_no,
			'trade_no': 'EPAY-1',
			'trade_status': 'TRADE_SUCCESS',
			'type': 'alipay',
			'money': '39.00',
		}
		payload['sign'] = _epay_test_sign(payload, 'secret')
		payload['sign_type'] = 'MD5'

		response = self.client.post(reverse('epay_notify'), payload)

		self.assertEqual(response.status_code, 200)
		order.refresh_from_db()
		self.assertEqual(order.status, PaymentOrder.Status.PAID)
		subscription = UserPlanSubscription.objects.get(user=user)
		self.assertEqual(subscription.plan_code, 'plus')
		self.assertTrue(subscription.is_active)

	def test_rules_page_exposes_current_normalization_settings(self):
		NormalizationSettings.current()
		ModelAlias.objects.create(source_model_name='claude-3-5-sonnet', target_model_name='claude-sonnet')

		response = self.client.get(reverse('watchlist_rules'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'data-rules-save-url')
		self.assertContains(response, 'claude-3-5-sonnet')
		self.assertContains(response, 'claude-sonnet')

	def test_save_rules_creates_alias_and_refreshes_snapshots(self):
		site = CompetitorSite.objects.create(base_url='https://alias.example.com', name='Alias Relay')
		fetch_run = FetchRun.objects.create(site=site, status=FetchRun.Status.SUCCESS, finished_at=timezone.now())
		snapshot = ModelPriceSnapshot.objects.create(
			fetch_run=fetch_run,
			site=site,
			model_name='claude-3.5-sonnet',
			normalized_model_name='claude-3-5-sonnet',
			quota_type=ModelPriceSnapshot.QuotaType.TOKEN,
		)

		response = self.client.post(reverse('rules_save'), {
			'default_usd_exchange_rate': '7.20',
			'ranking_mode': NormalizationSettings.RankingMode.INPUT_OUTPUT,
			'alias_source': ['claude-3.5-sonnet'],
			'alias_target': ['claude-sonnet'],
			'alias_note': ['合并旧命名'],
		})

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.json()['ok'])
		self.assertTrue(ModelAlias.objects.filter(source_model_name='claude-3-5-sonnet', target_model_name='claude-sonnet').exists())
		snapshot.refresh_from_db()
		self.assertEqual(snapshot.normalized_model_name, 'claude-sonnet')

	def test_new_site_uses_one_as_default_exchange_rate(self):
		settings_row = NormalizationSettings.current()
		settings_row.default_usd_exchange_rate = Decimal('7.20')
		settings_row.save()

		status_mock, pricing_mock = self._mock_site_save_collection(metadata={
			'name': 'Rate Default',
			'icon_url': '',
			'system_start_time': None,
			'system_version': '',
			'usd_exchange_rate': None,
		})
		with status_mock, pricing_mock:
			response = self.client.post(reverse('site_save'), {
				'base_url': 'rate-default.example.com',
				'name': 'Rate Default',
			})

		self.assertEqual(response.status_code, 200)
		self.assertEqual(CompetitorSite.objects.get(name='Rate Default').usd_exchange_rate, Decimal('1.000000'))


class EmailLoginTests(TestCase):
	@override_settings(DEBUG=True, EMAIL_HOST='', EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend')
	def test_send_code_prints_to_console_when_debug_email_is_unconfigured(self):
		stdout = StringIO()

		with patch('sys.stdout', stdout):
			response = self.client.post(reverse('login_send_code'), {'email': 'Hello@Example.com'})

		self.assertEqual(response.status_code, 200)
		self.assertEqual(LoginCode.objects.filter(email='hello@example.com').count(), 1)
		self.assertIn('[CheapToken] Login code for hello@example.com:', stdout.getvalue())

	@override_settings(DEBUG=True, EMAIL_HOST='', EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend')
	def test_send_code_is_rate_limited_by_email_cooldown(self):
		with patch('sys.stdout', StringIO()):
			first_response = self.client.post(reverse('login_send_code'), {'email': 'hello@example.com'})
			second_response = self.client.post(reverse('login_send_code'), {'email': 'hello@example.com'})

		self.assertEqual(first_response.status_code, 200)
		self.assertEqual(second_response.status_code, 429)
		self.assertEqual(LoginCode.objects.filter(email='hello@example.com').count(), 1)

	@override_settings(DEBUG=True, EMAIL_HOST='', EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', ARGUS_LOGIN_CODE_EMAIL_WINDOWS=[(600, 10)], ARGUS_LOGIN_CODE_IP_WINDOWS=[(600, 2)], ARGUS_LOGIN_CODE_COOLDOWN_SECONDS=0)
	def test_send_code_for_new_email_is_rate_limited_by_ip_window(self):
		with patch('sys.stdout', StringIO()):
			first_response = self.client.post(reverse('login_send_code'), {'email': 'first-new@example.com'})
			second_response = self.client.post(reverse('login_send_code'), {'email': 'second-new@example.com'})
			third_response = self.client.post(reverse('login_send_code'), {'email': 'third-new@example.com'})

		self.assertEqual(first_response.status_code, 200)
		self.assertEqual(second_response.status_code, 200)
		self.assertEqual(third_response.status_code, 429)
		self.assertIn('当前网络请求验证码过于频繁', third_response.json()['message'])

	@override_settings(DEBUG=True, EMAIL_HOST='', EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', ARGUS_LOGIN_CODE_EMAIL_WINDOWS=[(600, 10), (86400, 2)], ARGUS_LOGIN_CODE_IP_WINDOWS=[(600, 10)], ARGUS_LOGIN_CODE_COOLDOWN_SECONDS=0)
	def test_send_code_is_rate_limited_by_each_configured_window(self):
		with patch('sys.stdout', StringIO()):
			first_response = self.client.post(reverse('login_send_code'), {'email': 'hello@example.com'})
			second_response = self.client.post(reverse('login_send_code'), {'email': 'hello@example.com'})
			third_response = self.client.post(reverse('login_send_code'), {'email': 'hello@example.com'})

		self.assertEqual(first_response.status_code, 200)
		self.assertEqual(second_response.status_code, 200)
		self.assertEqual(third_response.status_code, 429)
		self.assertIn('验证码请求次数过多', third_response.json()['message'])

	@override_settings(DEBUG=True, EMAIL_HOST='', EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', ARGUS_LOGIN_CODE_EMAIL_WINDOWS=[(600, 3), (86400, 10)], ARGUS_LOGIN_CODE_IP_WINDOWS=[(600, 10), (3600, 30)], ARGUS_LOGIN_CODE_COOLDOWN_SECONDS=0)
	def test_ip_window_allows_more_users_than_email_window(self):
		with patch('sys.stdout', StringIO()):
			responses = [
				self.client.post(reverse('login_send_code'), {'email': f'company-user-{index}@example.com'})
				for index in range(10)
			]
			eleventh_response = self.client.post(reverse('login_send_code'), {'email': 'company-user-11@example.com'})

		self.assertTrue(all(response.status_code == 200 for response in responses))
		self.assertEqual(eleventh_response.status_code, 429)
		self.assertIn('当前网络请求验证码过于频繁', eleventh_response.json()['message'])

	@override_settings(DEBUG=True, ARGUS_LOGIN_CODE_MAX_ATTEMPTS=1)
	def test_verify_code_locks_after_failed_attempts(self):
		LoginCode.create_for_email(email='hello@example.com', code='123456')

		bad_response = self.client.post(reverse('login_verify_code'), {'email': 'hello@example.com', 'code': '000000'})
		good_response = self.client.post(reverse('login_verify_code'), {'email': 'hello@example.com', 'code': '123456'})

		login_code = LoginCode.objects.get(email='hello@example.com')
		self.assertEqual(bad_response.status_code, 400)
		self.assertEqual(good_response.status_code, 400)
		self.assertEqual(login_code.attempt_count, 1)

	@override_settings(DEBUG=True, EMAIL_HOST='', EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend')
	def test_verify_code_logs_user_in(self):
		with patch('sys.stdout', StringIO()):
			self.client.post(reverse('login_send_code'), {'email': 'hello@example.com'})

		login_code = LoginCode.objects.get(email='hello@example.com')
		with patch.object(LoginCode, 'verify', return_value=True):
			response = self.client.post(reverse('login_verify_code'), {'email': 'hello@example.com', 'code': '000000'})

		self.assertEqual(response.status_code, 200)
		login_code.refresh_from_db()
		self.assertIsNotNone(login_code.used_at)

	@override_settings(ARGUS_LOGIN_CODE_RETENTION_SECONDS=60 * 60 * 24 * 30)
	def test_purge_stale_login_codes_deletes_rows_older_than_retention(self):
		old_code = LoginCode.create_for_email(email='old@example.com', code='123456')
		fresh_code = LoginCode.create_for_email(email='fresh@example.com', code='123456')
		LoginCode.objects.filter(id=old_code.id).update(created_at=timezone.now() - timedelta(days=31))

		deleted_count = LoginCode.purge_stale()

		self.assertEqual(deleted_count, 1)
		self.assertFalse(LoginCode.objects.filter(id=old_code.id).exists())
		self.assertTrue(LoginCode.objects.filter(id=fresh_code.id).exists())

	@override_settings(ARGUS_LOGIN_CODE_RETENTION_SECONDS=60 * 60 * 24 * 30)
	def test_purge_login_codes_management_command(self):
		login_code = LoginCode.create_for_email(email='old@example.com', code='123456')
		LoginCode.objects.filter(id=login_code.id).update(created_at=timezone.now() - timedelta(days=31))
		stdout = StringIO()

		call_command('purge_login_codes', stdout=stdout)

		self.assertIn('Deleted 1 stale login code row(s).', stdout.getvalue())
		self.assertFalse(LoginCode.objects.filter(id=login_code.id).exists())


def _epay_test_sign(params, key):
	unsigned = '&'.join(
		f'{name}={params[name]}'
		for name in sorted(params.keys())
		if params[name] != '' and name not in {'sign', 'sign_type'}
	)
	return hashlib.md5((unsigned + key).encode('utf-8')).hexdigest()
