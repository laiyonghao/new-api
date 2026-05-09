# Argus Technical Solution

## 1. Design Goal

Argus should evolve from a local Django Admin tool into a small public SaaS, but it still must remain intentionally narrow.

The implementation should optimize for:

- low code volume
- small operational surface area
- user-owned monitored site lists
- predictable scheduled collection
- simple payment and email flows

Argus is not intended to become a public relay directory or a large workflow platform.

## 2. Product Architecture

Argus should be split into two logical layers.

### 2.1 Shared data collection layer

Stores:

- monitored sites
- fetch runs
- price snapshots
- normalized model names

This layer performs collection and comparison.

### 2.2 User account and billing layer

Stores:

- user identity
- login codes
- active subscription plan
- payment orders
- daily email history when needed for traceability

This layer controls who can log in, what plan they have, and how many sites they may monitor.

## 3. Technology Stack

- Python 3
- Django
- SQLite for current development, with future upgrade path to PostgreSQL/MySQL if needed
- Django templates for MVP user-facing pages
- HTMX for partial updates on user-facing pages
- Django Admin for internal operations
- requests for HTTP collection
- Django email backend for verification codes and digests
- Epay integration implemented in Python

Not used in MVP:

- DRF
- Celery
- Redis as a hard requirement
- message queue
- React
- Vue
- team permission system
- usage scenario solver

## 4. App Layout

Suggested logical modules inside `collector/` plus one new account/billing surface:

### 4.1 `collector.models`

Contains:

- `MonitoredSite`
- `FetchRun`
- `ModelPriceSnapshot`
- `LoginCode`
- `UserPlanSubscription`
- `PaymentOrder`

If code volume grows, account and payment models can move to dedicated apps later, but one app is acceptable for MVP.

### 4.2 `collector.services.discovery`

URL normalization and metadata discovery.

### 4.3 `collector.services.fetcher`

Remote collection and snapshot normalization.

### 4.4 `collector.services.comparison`

Builds comparison data scoped to one user.

### 4.5 `collector.services.auth`

Handles:

- login code generation
- login code validation
- lazy user creation
- session exclusivity enforcement support

### 4.6 `collector.services.billing`

Handles:

- plan lookup
- site-limit enforcement
- subscription activation/extension
- payment order completion

### 4.7 `collector.services.epay`

Minimal Epay client wrapper.

## 5. Data Model

## 5.1 User identity

MVP should continue using Django's built-in auth user table instead of introducing a custom user model now.

Recommended identity rule:

- email is the canonical login identifier
- on first successful verification, create user lazily
- set username deterministically from email if needed for compatibility

This avoids disruptive auth-model migration risk.

## 5.2 MonitoredSite

`MonitoredSite` is the target-state replacement for the current `CompetitorSite` model.

Recommended fields:

- id
- user foreign key
- base_url
- name
- note
- icon_url
- usd_exchange_rate
- enabled
- last_fetch_at
- last_fetch_status
- last_error
- last_manual_fetch_at
- created_at
- updated_at

Constraints:

- unique together: `(user, base_url)`
- ordering by name then base_url

## 5.3 FetchRun

Recommended fields:

- id
- site foreign key
- requested_url
- started_at
- finished_at
- status
- error_message
- http_status_code
- response_excerpt
- created_count
- trigger_source

`trigger_source` should distinguish:

- auto
- manual
- create

## 5.4 ModelPriceSnapshot

Recommended fields stay close to the current implementation:

- id
- fetch_run foreign key
- site foreign key
- model_name
- normalized_model_name
- vendor_name
- quota_type
- input_price_usd_per_1m
- output_price_usd_per_1m
- request_price_usd
- input_price_converted_per_1m
- output_price_converted_per_1m
- request_price_converted
- raw_model_ratio
- raw_completion_ratio
- raw_model_price
- raw_cache_ratio
- raw_create_cache_ratio
- billing_mode
- billing_expr
- supported_endpoint_types_json
- raw_enable_groups_json
- snapshot_at
- created_at

Indexes:

- normalized_model_name
- site + normalized_model_name
- fetch_run

## 5.5 LoginCode

Purpose: one-time login code verification.

Recommended fields:

- id
- email
- code_hash
- client_ip
- purpose
- expires_at
- used_at
- created_at

Rules:

- store only hash, not plaintext
- code should expire quickly, e.g. 10 minutes
- code is single-use

## 5.6 UserPlanSubscription

Purpose: current plan state per user.

Recommended fields:

- id
- user
- plan_code
- status
- starts_at
- expires_at
- auto_renew optional false by default
- created_at
- updated_at

Plan codes:

- free
- pro
- plus
- max

## 5.7 PaymentOrder

Purpose: Epay purchase order tracking.

Recommended fields:

- id
- user
- trade_no
- provider
- payment_method
- plan_code
- billing_cycle
- amount_rmb
- status
- provider_payload_json
- paid_at
- created_at
- updated_at

`billing_cycle` examples:

- quarter
- year
- month

## 6. Authentication and Session Design

## 6.1 Email-code login

Implementation flow:

1. POST email to send-code endpoint
2. validate rate limits
3. generate random numeric code
4. hash and store it in `LoginCode`
5. send via email
6. POST email + code to verify endpoint
7. verify latest valid unused code
8. create or find Django user
9. rotate session and enforce exclusivity

## 6.2 Rate limiting

Recommended library:

- `django-ratelimit`

Recommended backend for counters in MVP:

- Django database cache backend, or Redis if already available later

The send-code endpoint should apply two independent limit keys:

- key by normalized email
- key by client IP

Required windows:

- 1/minute and 3/10 minutes for email
- 1/minute and 3/10 minutes for IP

## 6.3 Session exclusivity

Recommended implementation:

1. store `active_session_key` on a lightweight user state record or in the user profile extension table
2. on successful login, create a new session and overwrite `active_session_key`
3. middleware checks that the current session key matches the stored active key
4. mismatch means force logout

This keeps the rule simple and deterministic.

## 7. Site Collection Design

## 7.1 Adding a site

When a user submits a URL:

1. normalize to base URL
2. check `(user, base_url)` uniqueness
3. validate plan site limit before insert
4. auto-discover metadata
5. create `MonitoredSite`
6. trigger first collection

## 7.2 Manual collection

Manual collection should check:

- user owns the site
- site is enabled
- last manual collection was at least 1 hour ago

If allowed, create `FetchRun` with `trigger_source=manual`.

## 7.3 Automatic collection scheduler

MVP should avoid Celery and use management commands invoked by cron or system scheduler.

Recommended commands:

- `python manage.py collect_due_sites`
- `python manage.py send_daily_digest`
- `python manage.py purge_login_codes`

Suggested fixed schedule:

- Free sites: once daily before morning digest
- Pro/Plus/Max: three fixed windows daily, e.g. morning / afternoon / evening
- Daily digest: 08:00, based on latest successful snapshots already collected

## 8. Comparison Logic

Comparison must always be scoped by current user.

Query rule:

1. fetch sites owned by current user and enabled
2. find latest successful `FetchRun` for each site
3. gather `ModelPriceSnapshot` rows from those runs
4. compare converted price fields only

Required outputs:

- cheapest input site and converted input price
- cheapest output site and converted output price
- cheapest request site and converted request price

Dynamic billing snapshots should be excluded from exact cheapest ranking.

## 9. Daily Email Digest

The digest replaces separate follow/alert/notification models for MVP.

Implementation approach:

1. run one scheduled command at 08:00
2. for each active user, gather all enabled monitored sites
3. compile latest collection status and recent price-change summary
4. render email template
5. send through Django email backend

The digest should include deep links such as:

- monitored site detail page
- comparison page pre-filtered to that user's site list

## 10. Email Delivery

Argus should rely on Django's SMTP email backend configured via environment variables.

Recommended settings mapping:

- `ARGUS_EMAIL_BACKEND` -> `EMAIL_BACKEND`
- `ARGUS_EMAIL_HOST` -> `EMAIL_HOST`
- `ARGUS_EMAIL_PORT` -> `EMAIL_PORT`
- `ARGUS_EMAIL_USE_TLS` -> `EMAIL_USE_TLS`
- `ARGUS_EMAIL_HOST_USER` -> `EMAIL_HOST_USER`
- `ARGUS_EMAIL_HOST_PASSWORD` -> `EMAIL_HOST_PASSWORD`
- `ARGUS_EMAIL_FROM` -> `DEFAULT_FROM_EMAIL`

The verification email and daily digest should share the same backend.

## 11. Billing and Plan Enforcement

## 11.1 Plan metadata

Keep plan definitions in code for MVP.

Recommended plan table in Python constants:

- free: 2 sites, 1 auto/day, manual cooldown 1 hour
- pro-quarter: 50 RMB / quarter
- pro-year: 100 RMB / year
- plus-month: 50 RMB / month
- plus-year: 300 RMB / year
- max-year: 1000 RMB / year

Runtime plan capabilities should normalize to:

- free
- pro
- plus
- max

## 11.2 Enforcement points

The backend must enforce limits at:

- site creation
- site re-enable if disabled sites exceed plan cap
- auto collection scheduler selection

Manual fetch cooldown is independent of plan tier and remains 1 hour for all tiers.

## 12. Epay Integration

## 12.1 Reference flow

The existing Go implementation in the main project uses a small Epay client abstraction for two essential operations:

- purchase request creation
- callback verification

Argus should follow the same flow shape in Python.

## 12.2 Python implementation choice

No clearly reusable Python SDK was identified during quick search.

Therefore MVP should plan for an internal minimal client with:

- endpoint base URL
- pid
- key
- purchase request builder
- sign generator
- notify/return verifier

This client should be intentionally small and only cover the flows Argus needs.

## 12.3 Payment flow

1. user selects plan and billing cycle
2. create pending `PaymentOrder`
3. call Epay purchase endpoint
4. redirect user to payment page
5. Epay notify callback verifies success and completes order
6. subscription is activated or extended
7. return callback redirects browser to billing result page

## 13. Internal Admin and User UI

### 13.1 Keep Django Admin

Django Admin should remain the operator back office for:

- debugging sites
- reviewing fetch failures
- checking payment orders
- checking user subscriptions

### 13.2 Thin user-facing pages

MVP user UI only needs:

- email login pages
- monitored site list
- add/edit monitored site page
- comparison page
- billing page
- account page

No complex SPA is required in this phase.

### 13.3 Frontend rendering strategy

User-facing pages should use server-side rendering first.

Recommended stack split:

- Django templates render full pages
- HTMX handles partial replacement for forms, filters, manual refresh actions, and inline status updates
- a very small amount of vanilla JavaScript may be added for progressive enhancement when HTMX is not the right fit

Reasons:

- login, CSRF, session, and rate-limit flows stay aligned with Django defaults
- no duplicate API contract is needed for the web UI
- the product mostly consists of forms, lists, tables, and filtered comparison views
- the development cost stays low while preserving a polished user experience

### 13.4 Frontend information architecture

Suggested page set:

- marketing / landing page
- email login page
- monitored site list page
- monitored site create/edit page
- comparison page
- billing page
- account page

Suggested HTMX slices:

- login code send form status area
- monitored site list table or card list refresh
- add-site form validation and submit result area
- manual collection status card per site
- comparison filter form and result table
- billing order creation result panel

Suggested template layout:

- `templates/base.html` for global shell
- `templates/partials/` for reusable cards, forms, states, and nav fragments
- `templates/pages/` for full pages

### 13.5 Frontend state model

Keep frontend state shallow.

State should normally live in one of three places:

- query parameters for filters, sort, and page mode
- Django form state for validation errors and success states
- HTMX target containers for partial refresh results

Avoid building a client-side state store in MVP.

### 13.6 Frontend visual language

Argus should not look like a default admin panel.

The visual direction should be:

- warm off-white backgrounds instead of stark white
- dark brown-black text instead of pure black
- terracotta or cinnamon accent color instead of saturated blue
- generous spacing and rounded cards
- editorial typography and restrained UI density

The dedicated reference and token guidance should live in a separate design document so implementation can stay consistent across templates.

## 14. Environment Variables

Suggested `.env` contract:

### 14.1 Core

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `ARGUS_ALLOWED_HOSTS`
- `ARGUS_HTTP_TIMEOUT_SECONDS`

### 14.2 Email

- `ARGUS_EMAIL_BACKEND`
- `ARGUS_EMAIL_HOST`
- `ARGUS_EMAIL_PORT`
- `ARGUS_EMAIL_USE_TLS`
- `ARGUS_EMAIL_HOST_USER`
- `ARGUS_EMAIL_HOST_PASSWORD`
- `ARGUS_EMAIL_FROM`

### 14.3 Auth

- `ARGUS_LOGIN_CODE_TTL_SECONDS`
- `ARGUS_LOGIN_CODE_RETENTION_SECONDS`, default `2592000` seconds / 30 days
- `ARGUS_LOGIN_CODE_COOLDOWN_SECONDS`
- `ARGUS_LOGIN_CODE_EMAIL_WINDOWS`, e.g. `[(600, 3), (86400, 10)]`
- `ARGUS_LOGIN_CODE_IP_WINDOWS`, e.g. `[(600, 10), (3600, 30)]`
- `ARGUS_LOGIN_CODE_MAX_ATTEMPTS`
- `ARGUS_SESSION_COOKIE_AGE_SECONDS`

### 14.4 Payment

- `ARGUS_EPAY_ENABLED`
- `ARGUS_EPAY_URL`
- `ARGUS_EPAY_PID`
- `ARGUS_EPAY_KEY`
- `ARGUS_EPAY_NOTIFY_URL`
- `ARGUS_EPAY_RETURN_URL`

## 15. Delivery Sequence

Recommended implementation order:

1. convert `CompetitorSite` semantics to `MonitoredSite` with user ownership
2. add thin email-code login flow
3. add send-code rate limiting
4. add exclusive session enforcement
5. add user-scoped monitored-site pages
6. add plan limits and manual-fetch cooldown enforcement
7. add scheduled collection commands
8. add daily digest email command
9. add Epay purchase and callback flow
10. polish billing and account pages

This order keeps the product usable early while deferring payment until the core monitoring loop is already working.