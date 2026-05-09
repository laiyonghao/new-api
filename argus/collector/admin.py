from django.contrib import admin, messages
from django.db.models import Count
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from .models import CompetitorSite, FetchRun, LoginCode, ModelAlias, ModelPriceSnapshot, NormalizationSettings, PaymentOrder, UserPlanSubscription, UserSessionState
from .services.comparison import build_comparison_context
from .services.discovery import discover_site_metadata, discover_site_status_metadata
from .services.fetcher import collect_site_pricing


admin.site.site_header = 'CheapToken'
admin.site.site_title = 'CheapToken Admin'
admin.site.index_title = 'AI Relay Pricing Watch'


@admin.register(CompetitorSite)
class CompetitorSiteAdmin(admin.ModelAdmin):
	change_list_template = 'admin/collector/competitorsite/change_list.html'
	list_display = (
		'site_identity',
		'base_url_link',
		'owner_display',
		'enabled',
		'fetch_status_badge',
		'snapshot_count_display',
		'usd_rate_display',
		'system_version_display',
		'system_start_time_display',
		'last_fetch_at_display',
		'short_last_error',
		'site_admin_actions',
	)
	list_display_links = ('site_identity', 'base_url_link')
	list_filter = ('enabled', 'last_fetch_status', 'owner')
	search_fields = ('name', 'base_url', 'note', 'system_version', 'owner__username', 'owner__email')
	list_select_related = ('owner',)
	list_per_page = 50
	date_hierarchy = 'last_fetch_at'
	readonly_fields = (
		'icon_preview',
		'system_start_time_display',
		'snapshot_count_display',
		'latest_fetch_run_link',
		'last_fetch_at',
		'last_fetch_status',
		'last_error',
		'created_at',
		'updated_at',
	)
	actions = ('collect_selected_sites', 'refresh_status_metadata_for_selected_sites', 'enable_selected_sites', 'disable_selected_sites')
	fieldsets = (
		('Site', {'fields': ('owner', 'base_url', 'name', 'note', 'icon_url', 'icon_preview', 'enabled', 'usd_exchange_rate')}),
		('Status Metadata', {'fields': ('system_version', 'system_start_time', 'system_start_time_display')}),
		('Fetch Summary', {'fields': ('snapshot_count_display', 'latest_fetch_run_link', 'last_fetch_at', 'last_fetch_status', 'last_error')}),
		('Metadata', {'fields': ('created_at', 'updated_at')}),
	)
	ordering = ('name', 'base_url')

	def get_queryset(self, request):
		return super().get_queryset(request).annotate(snapshot_total=Count('snapshots', distinct=True))

	def get_urls(self):
		urls = super().get_urls()
		custom_urls = [
			path(
				'<int:object_id>/collect/',
				self.admin_site.admin_view(self.collect_site_view),
				name='collector_competitorsite_collect_one',
			),
			path(
				'<int:object_id>/refresh-status/',
				self.admin_site.admin_view(self.refresh_status_view),
				name='collector_competitorsite_refresh_status',
			),
			path(
				'collect-all/',
				self.admin_site.admin_view(self.collect_all_view),
				name='collector_competitorsite_collect_all',
			),
			path(
				'comparison/',
				self.admin_site.admin_view(self.comparison_view),
				name='collector_competitorsite_comparison',
			),
		]
		return custom_urls + urls

	def changelist_view(self, request, extra_context=None):
		extra_context = extra_context or {}
		extra_context['collect_all_url'] = reverse('admin:collector_competitorsite_collect_all')
		extra_context['comparison_url'] = reverse('admin:collector_competitorsite_comparison')
		return super().changelist_view(request, extra_context=extra_context)

	@admin.display(description='Site', ordering='name')
	def site_identity(self, obj: CompetitorSite):
		name = obj.name or obj.base_url
		if obj.icon_url:
			return format_html(
				'<div style="display:flex;align-items:center;gap:0.55rem;min-width:180px;">'
				'<img src="{}" alt="" style="width:28px;height:28px;border-radius:7px;object-fit:cover;border:1px solid #d0d7de;background:#fff;">'
				'<strong>{}</strong></div>',
				obj.icon_url,
				name,
			)
		return format_html('<strong>{}</strong>', name)

	@admin.display(description='Base URL', ordering='base_url')
	def base_url_link(self, obj: CompetitorSite):
		return format_html('<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>', obj.base_url, obj.base_url)

	@admin.display(description='Owner', ordering='owner__email')
	def owner_display(self, obj: CompetitorSite):
		if not obj.owner_id:
			return 'Public'
		return obj.owner.email or obj.owner.username or obj.owner_id

	@admin.display(description='Status', ordering='last_fetch_status')
	def fetch_status_badge(self, obj: CompetitorSite):
		colors = {
			CompetitorSite.FetchStatus.SUCCESS: ('#dcfce7', '#166534', 'Success'),
			CompetitorSite.FetchStatus.FAILED: ('#fee2e2', '#991b1b', 'Failed'),
			CompetitorSite.FetchStatus.NEVER: ('#f3f4f6', '#374151', 'Never'),
		}
		background, color, label = colors.get(obj.last_fetch_status, ('#f3f4f6', '#374151', obj.last_fetch_status))
		return format_html(
			'<span style="display:inline-flex;align-items:center;border-radius:999px;padding:0.15rem 0.55rem;background:{};color:{};font-weight:700;font-size:12px;">{}</span>',
			background,
			color,
			label,
		)

	@admin.display(description='Snapshots', ordering='snapshot_total')
	def snapshot_count_display(self, obj: CompetitorSite):
		return getattr(obj, 'snapshot_total', None) if hasattr(obj, 'snapshot_total') else obj.snapshots.count()

	@admin.display(description='USD Rate', ordering='usd_exchange_rate')
	def usd_rate_display(self, obj: CompetitorSite):
		return obj.usd_exchange_rate

	@admin.display(description='Version', ordering='system_version')
	def system_version_display(self, obj: CompetitorSite):
		return obj.system_version or '-'

	@admin.display(description='Start Time', ordering='system_start_time')
	def system_start_time_display(self, obj: CompetitorSite):
		if not obj.system_start_time:
			return '-'
		started_at = timezone.datetime.fromtimestamp(obj.system_start_time, tz=timezone.get_current_timezone())
		return timezone.localtime(started_at).strftime('%Y-%m-%d %H:%M:%S')

	@admin.display(description='Last Fetch', ordering='last_fetch_at')
	def last_fetch_at_display(self, obj: CompetitorSite):
		if not obj.last_fetch_at:
			return '-'
		return timezone.localtime(obj.last_fetch_at).strftime('%Y-%m-%d %H:%M:%S')

	@admin.display(description='Logo')
	def icon_preview(self, obj: CompetitorSite):
		if not obj.icon_url:
			return '-'
		return format_html('<img src="{}" alt="" style="width:48px;height:48px;border-radius:10px;object-fit:cover;border:1px solid #d0d7de;background:#fff;">', obj.icon_url)

	@admin.display(description='Latest Fetch Run')
	def latest_fetch_run_link(self, obj: CompetitorSite):
		fetch_run = obj.fetch_runs.first()
		if not fetch_run:
			return '-'
		url = reverse('admin:collector_fetchrun_change', args=[fetch_run.pk])
		label = f'{fetch_run.get_status_display()} · {fetch_run.created_count} snapshots'
		return format_html('<a href="{}">{}</a>', url, label)

	@admin.display(description='Manage')
	def site_admin_actions(self, obj: CompetitorSite):
		collect_url = reverse('admin:collector_competitorsite_collect_one', args=[obj.pk])
		refresh_url = reverse('admin:collector_competitorsite_refresh_status', args=[obj.pk])
		return format_html(
			'<div style="display:flex;gap:0.4rem;white-space:nowrap;"><a class="button" href="{}">Collect</a><a class="button" href="{}">Refresh status</a></div>',
			collect_url,
			refresh_url,
		)

	@admin.display(description='Last Error')
	def short_last_error(self, obj: CompetitorSite):
		if not obj.last_error:
			return '-'
		return obj.last_error[:120]

	@admin.action(description='Collect selected sites')
	def collect_selected_sites(self, request, queryset):
		self._collect_queryset(request, queryset.order_by('id'))

	@admin.action(description='Refresh /api/status metadata for selected sites')
	def refresh_status_metadata_for_selected_sites(self, request, queryset):
		updated_count = 0
		warning_messages = []
		for site in queryset.order_by('id'):
			updated_fields, errors = self._refresh_status_metadata(site)
			if updated_fields:
				updated_count += 1
			if errors:
				warning_messages.append(f'{site}: ' + '; '.join(errors))
		message = f'Refreshed status metadata for {updated_count} site(s).'
		if warning_messages:
			message += ' Partial failures: ' + ' | '.join(warning_messages[:5])
		self.message_user(request, message, level=messages.WARNING if warning_messages else messages.SUCCESS)

	@admin.action(description='Enable selected sites')
	def enable_selected_sites(self, request, queryset):
		updated = queryset.update(enabled=True)
		self.message_user(request, f'Enabled {updated} site(s).', level=messages.SUCCESS)

	@admin.action(description='Disable selected sites')
	def disable_selected_sites(self, request, queryset):
		updated = queryset.update(enabled=False)
		self.message_user(request, f'Disabled {updated} site(s).', level=messages.SUCCESS)

	def save_model(self, request, obj, form, change):
		super().save_model(request, obj, form, change)

		if not change or 'base_url' in form.changed_data or not obj.name or not obj.icon_url or not obj.system_version or not obj.system_start_time:
			status_fields, status_errors = self._refresh_status_metadata(obj)
			if status_fields:
				self.message_user(request, 'Updated status metadata: ' + ', '.join(status_fields) + '.', level=messages.SUCCESS)
			if status_errors:
				self.message_user(request, 'Status metadata refresh had partial failures: ' + '; '.join(status_errors), level=messages.WARNING)

		if not change or 'base_url' in form.changed_data or not obj.name or not obj.note or not obj.icon_url:
			discovery_errors = []
			metadata = discover_site_metadata(obj.base_url, errors=discovery_errors, include_status=False)
			updated_fields = []
			if metadata.get('name') and not obj.name:
				obj.name = metadata['name']
				updated_fields.append('name')
			if metadata.get('note') and not obj.note:
				obj.note = metadata['note']
				updated_fields.append('note')
			if metadata.get('icon_url') and not obj.icon_url:
				obj.icon_url = metadata['icon_url']
				updated_fields.append('icon_url')
			if updated_fields:
				updated_fields.append('updated_at')
				obj.save(update_fields=updated_fields)
			if discovery_errors:
				self.message_user(
					request,
					'Site metadata discovery had partial failures: ' + '; '.join(discovery_errors),
					level=messages.WARNING,
				)

		if not change or 'base_url' in form.changed_data or 'usd_exchange_rate' in form.changed_data:
			fetch_run = collect_site_pricing(obj)
			if fetch_run.status == FetchRun.Status.SUCCESS:
				self.message_user(
					request,
					f'Collected {fetch_run.created_count} pricing snapshot(s) for {obj}.',
					level=messages.SUCCESS,
				)
			else:
				self.message_user(
					request,
					f'Collection failed for {obj}: {fetch_run.error_message}',
					level=messages.WARNING,
				)

	def collect_site_view(self, request, object_id):
		site = self.get_object(request, object_id)
		if site is None:
			self.message_user(request, 'Site does not exist.', level=messages.ERROR)
			return HttpResponseRedirect(reverse('admin:collector_competitorsite_changelist'))
		fetch_run = collect_site_pricing(site)
		if fetch_run.status == FetchRun.Status.SUCCESS:
			self.message_user(request, f'Collected {fetch_run.created_count} pricing snapshot(s) for {site}.', level=messages.SUCCESS)
		else:
			self.message_user(request, f'Collection failed for {site}: {fetch_run.error_message}', level=messages.WARNING)
		return HttpResponseRedirect(reverse('admin:collector_competitorsite_changelist'))

	def refresh_status_view(self, request, object_id):
		site = self.get_object(request, object_id)
		if site is None:
			self.message_user(request, 'Site does not exist.', level=messages.ERROR)
			return HttpResponseRedirect(reverse('admin:collector_competitorsite_changelist'))
		updated_fields, errors = self._refresh_status_metadata(site)
		if updated_fields:
			self.message_user(request, f'Updated status metadata for {site}: ' + ', '.join(updated_fields) + '.', level=messages.SUCCESS)
		else:
			self.message_user(request, f'No status metadata changed for {site}.', level=messages.INFO)
		if errors:
			self.message_user(request, 'Status metadata refresh had partial failures: ' + '; '.join(errors), level=messages.WARNING)
		return HttpResponseRedirect(reverse('admin:collector_competitorsite_changelist'))

	def collect_all_view(self, request):
		queryset = CompetitorSite.objects.filter(enabled=True).order_by('id')
		self._collect_queryset(request, queryset)
		return HttpResponseRedirect(reverse('admin:collector_competitorsite_changelist'))

	def comparison_view(self, request):
		context = {
			**self.admin_site.each_context(request),
			'opts': self.model._meta,
			'title': 'Cheapest Competitor Comparison',
			**build_comparison_context(request.GET, all_label='All'),
		}
		return render(request, 'admin/collector/comparison.html', context)

	def _collect_queryset(self, request, queryset):
		success_count = 0
		failure_count = 0
		for site in queryset:
			fetch_run = collect_site_pricing(site)
			if fetch_run.status == FetchRun.Status.SUCCESS:
				success_count += 1
			else:
				failure_count += 1
		self.message_user(
			request,
			f'Collection finished. Success: {success_count}, Failed: {failure_count}.',
			level=messages.SUCCESS if failure_count == 0 else messages.WARNING,
		)

	def _refresh_status_metadata(self, site: CompetitorSite):
		errors = []
		metadata = discover_site_status_metadata(site.base_url, errors=errors)
		updated_fields = []
		if metadata.get('name') and not site.name:
			site.name = metadata['name']
			updated_fields.append('name')
		if metadata.get('icon_url') and site.icon_url != metadata['icon_url']:
			site.icon_url = metadata['icon_url']
			updated_fields.append('icon_url')
		if metadata.get('system_start_time') is not None and metadata.get('system_start_time') != site.system_start_time:
			site.system_start_time = metadata.get('system_start_time')
			updated_fields.append('system_start_time')
		if metadata.get('system_version', '') != site.system_version:
			site.system_version = metadata.get('system_version', '')
			updated_fields.append('system_version')
		if metadata.get('usd_exchange_rate') and metadata['usd_exchange_rate'] != site.usd_exchange_rate:
			site.usd_exchange_rate = metadata['usd_exchange_rate']
			updated_fields.append('usd_exchange_rate')
		if updated_fields:
			site.save(update_fields=updated_fields + ['updated_at'])
		return updated_fields, errors


@admin.register(FetchRun)
class FetchRunAdmin(admin.ModelAdmin):
	list_display = ('site', 'started_at', 'finished_at', 'status', 'http_status_code', 'created_count')
	list_filter = ('status', 'site')
	search_fields = ('site__name', 'site__base_url', 'error_message')
	readonly_fields = (
		'site',
		'requested_url',
		'started_at',
		'finished_at',
		'status',
		'error_message',
		'http_status_code',
		'response_excerpt',
		'created_count',
		'created_at',
	)

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False


@admin.register(ModelPriceSnapshot)
class ModelPriceSnapshotAdmin(admin.ModelAdmin):
	list_display = (
		'model_name',
		'normalized_model_name',
		'vendor_name',
		'supported_endpoint_types_display',
		'site',
		'quota_type',
		'input_price_converted_display',
		'output_price_converted_display',
		'request_price_converted_display',
		'billing_mode',
		'snapshot_at',
	)
	list_filter = ('quota_type', 'site', 'billing_mode')
	search_fields = ('model_name', 'normalized_model_name', 'vendor_name', 'site__name', 'site__base_url')
	readonly_fields = (
		'fetch_run',
		'site',
		'model_name',
		'normalized_model_name',
		'vendor_name',
		'quota_type',
		'input_price_usd_per_1m',
		'output_price_usd_per_1m',
		'request_price_usd',
		'input_price_converted_per_1m',
		'output_price_converted_per_1m',
		'request_price_converted',
		'raw_model_ratio',
		'raw_completion_ratio',
		'raw_model_price',
		'raw_cache_ratio',
		'raw_create_cache_ratio',
		'billing_mode',
		'billing_expr',
		'supported_endpoint_types_display',
		'raw_enable_groups_display',
		'snapshot_at',
		'created_at',
	)
	fields = readonly_fields

	def _render_tag_list(self, values):
		if not values:
			return '-'
		return format_html(
			'<div style="display:flex;flex-wrap:wrap;gap:0.35rem;max-width:720px;">{}</div>',
			format_html_join(
				'',
				'<span style="display:inline-flex;align-items:center;padding:0.12rem 0.5rem;border:1px solid #d0d7de;border-radius:999px;background:#f6f8fa;color:#24292f;font-size:12px;line-height:1.6;">{}</span>',
				((value,) for value in values),
			),
		)

	@admin.display(description='Supported Endpoint Types')
	def supported_endpoint_types_display(self, obj: ModelPriceSnapshot):
		return self._render_tag_list(obj.supported_endpoint_types)

	@admin.display(description='Actual Input Price / 1M', ordering='input_price_converted_per_1m')
	def input_price_converted_display(self, obj: ModelPriceSnapshot):
		return obj.input_price_converted_per_1m

	@admin.display(description='Actual Output Price / 1M', ordering='output_price_converted_per_1m')
	def output_price_converted_display(self, obj: ModelPriceSnapshot):
		return obj.output_price_converted_per_1m

	@admin.display(description='Actual Request Price', ordering='request_price_converted')
	def request_price_converted_display(self, obj: ModelPriceSnapshot):
		return obj.request_price_converted

	@admin.display(description='Raw Enable Groups')
	def raw_enable_groups_display(self, obj: ModelPriceSnapshot):
		return self._render_tag_list(obj.raw_enable_groups)

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False


@admin.register(ModelAlias)
class ModelAliasAdmin(admin.ModelAdmin):
	list_display = ('source_model_name', 'target_model_name', 'enabled', 'updated_at')
	list_filter = ('enabled',)
	search_fields = ('source_model_name', 'target_model_name', 'note')
	readonly_fields = ('created_at', 'updated_at')


@admin.register(NormalizationSettings)
class NormalizationSettingsAdmin(admin.ModelAdmin):
	list_display = ('id', 'default_usd_exchange_rate', 'ranking_mode', 'updated_at')
	readonly_fields = ('updated_at',)

	def has_add_permission(self, request):
		return not NormalizationSettings.objects.exists()


@admin.register(LoginCode)
class LoginCodeAdmin(admin.ModelAdmin):
	list_display = ('email', 'request_ip', 'expires_at', 'attempt_count', 'used_at', 'created_at')
	list_filter = ('used_at', 'expires_at')
	search_fields = ('email', 'request_ip')
	readonly_fields = ('email', 'code_hash', 'request_ip', 'expires_at', 'attempt_count', 'used_at', 'created_at')
	date_hierarchy = 'created_at'

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False


@admin.register(UserSessionState)
class UserSessionStateAdmin(admin.ModelAdmin):
	list_display = ('user', 'active_session_key', 'updated_at')
	search_fields = ('user__username', 'user__email', 'active_session_key')
	readonly_fields = ('updated_at',)


@admin.register(UserPlanSubscription)
class UserPlanSubscriptionAdmin(admin.ModelAdmin):
	list_display = ('user', 'plan_code', 'status', 'starts_at', 'expires_at', 'auto_renew')
	list_filter = ('plan_code', 'status', 'auto_renew')
	search_fields = ('user__username', 'user__email', 'plan_code')
	date_hierarchy = 'starts_at'
	readonly_fields = ('created_at', 'updated_at')


@admin.register(PaymentOrder)
class PaymentOrderAdmin(admin.ModelAdmin):
	list_display = ('trade_no', 'user', 'plan_code', 'billing_cycle', 'amount_rmb', 'status', 'payment_method', 'paid_at', 'created_at')
	list_filter = ('status', 'plan_code', 'billing_cycle', 'payment_method')
	search_fields = ('trade_no', 'user__username', 'user__email', 'provider_payload_json')
	date_hierarchy = 'created_at'
	readonly_fields = ('trade_no', 'provider', 'provider_payload_json', 'paid_at', 'created_at', 'updated_at')
