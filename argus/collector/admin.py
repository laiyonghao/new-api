from django.contrib import admin, messages
from django.utils.html import format_html, format_html_join
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse

from .models import CompetitorSite, FetchRun, ModelPriceSnapshot
from .services.comparison import build_comparison_context
from .services.discovery import discover_site_metadata
from .services.fetcher import collect_site_pricing


admin.site.site_header = 'Argus'
admin.site.site_title = 'Argus Admin'
admin.site.index_title = 'Competitor Pricing Watch'


@admin.register(CompetitorSite)
class CompetitorSiteAdmin(admin.ModelAdmin):
	change_list_template = 'admin/collector/competitorsite/change_list.html'
	list_display = (
		'display_name',
		'base_url',
		'enabled',
		'usd_exchange_rate',
		'last_fetch_at',
		'last_fetch_status',
		'short_last_error',
	)
	list_filter = ('enabled', 'last_fetch_status')
	search_fields = ('name', 'base_url', 'note')
	readonly_fields = ('last_fetch_at', 'last_fetch_status', 'last_error', 'created_at', 'updated_at')
	actions = ('collect_selected_sites', 'enable_selected_sites', 'disable_selected_sites')
	fieldsets = (
		('Site', {'fields': ('base_url', 'name', 'note', 'icon_url', 'enabled', 'usd_exchange_rate')}),
		('Fetch Summary', {'fields': ('last_fetch_at', 'last_fetch_status', 'last_error')}),
		('Metadata', {'fields': ('created_at', 'updated_at')}),
	)

	def get_urls(self):
		urls = super().get_urls()
		custom_urls = [
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

	@admin.display(description='Name')
	def display_name(self, obj: CompetitorSite):
		return obj.name or '-'

	@admin.display(description='Last Error')
	def short_last_error(self, obj: CompetitorSite):
		if not obj.last_error:
			return '-'
		return obj.last_error[:80]

	@admin.action(description='Collect selected sites')
	def collect_selected_sites(self, request, queryset):
		self._collect_queryset(request, queryset.order_by('id'))

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

		if not change or 'base_url' in form.changed_data or not obj.name or not obj.note or not obj.icon_url:
			discovery_errors = []
			metadata = discover_site_metadata(obj.base_url, errors=discovery_errors)
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
