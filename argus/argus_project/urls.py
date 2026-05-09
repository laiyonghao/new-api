"""
URL configuration for argus_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path

from collector import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('index.html', views.home_view, name='prototype_home'),
    path('preview-site/', views.home_site_submit, name='home_site_submit'),
    path('watchlist/sites.html', views.page_view, {'page': 'watchlist/sites.html'}, name='watchlist_sites'),
    path('watchlist/comparison.html', views.page_view, {'page': 'watchlist/comparison.html'}, name='watchlist_comparison'),
    path('watchlist/custom-comparison.html', views.page_view, {'page': 'watchlist/custom-comparison.html'}, name='watchlist_custom_comparison'),
    path('watchlist/fetch-runs.html', views.page_view, {'page': 'watchlist/fetch-runs.html'}, name='watchlist_fetch_runs'),
    path('watchlist/rules.html', views.page_view, {'page': 'watchlist/rules.html'}, name='watchlist_rules'),
    path('watchlist/site-form.html', views.site_form_redirect, name='watchlist_site_form'),
    path('pricing/billing.html', views.page_view, {'page': 'pricing/billing.html'}, name='pricing_billing'),
    path('account/login.html', views.login_view, name='login'),
    path('account/account.html', views.page_view, {'page': 'account/account.html'}, name='account'),
    path('comparison/', views.comparison_view, name='comparison'),
    path('auth/send-code/', views.send_login_code, name='login_send_code'),
    path('auth/verify-code/', views.verify_login_code, name='login_verify_code'),
    path('auth/logout/', views.logout_view, name='logout'),
    path('pricing/checkout/', views.create_checkout_order, name='pricing_checkout'),
    path('pricing/epay/notify/', views.epay_notify, name='epay_notify'),
    path('pricing/epay/return/', views.epay_return, name='epay_return'),
    path('watchlist/rules/save/', views.save_normalization_rules, name='rules_save'),
    path('watchlist/sites/save/', views.save_site, name='site_save'),
    path('watchlist/sites/deactivate/', views.deactivate_site, name='site_deactivate'),
    path('watchlist/sites/fetch/', views.fetch_site, name='site_fetch'),
    path('admin/', admin.site.urls),
]
