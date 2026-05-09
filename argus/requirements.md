# Argus Requirements

## 1. Positioning

Argus is no longer an internal competitor-monitoring tool.

Its new MVP is a small public SaaS for individual AI relay users.

Core value:

- users input the relay sites they can personally access
- Argus continuously collects public pricing data from those sites
- Argus helps users compare prices only within their own monitored list
- Argus sends a daily email summary so users can quickly review the latest situation

This product does not maintain a public relay directory and does not publish a platform-wide ranking.

## 2. Product Goal

The MVP should solve one narrow problem:

help an individual user maintain a private watchlist of relay sites and decide, within that watchlist, which site is currently cheaper for a given model.

The MVP is intentionally lightweight.

It should provide:

1. email-code login
2. personal monitored site list
3. static price comparison inside that personal list
4. automatic scheduled collection
5. one daily email summary at 08:00
6. paid plans with higher site limits and collection frequency

## 2.1 Frontend experience principle

The MVP frontend should feel familiar to AI-tool users, but it must stay simple to build and cheap to maintain.

Required direction:

- Django templates for full-page rendering
- HTMX for partial refresh, inline form handling, and lightweight async states
- no React or Vue in MVP
- warm, editorial, Claude-adjacent visual language instead of a generic admin dashboard look
- design language defined in a separate frontend design document

The user-facing UI should look trustworthy and calm rather than highly technical or highly gamified.

## 3. Scope

### 3.1 In scope

- personal account system
- email + verification code login
- per-user monitored site list
- public pricing collection from compatible new-api instances
- static comparison based on latest successful snapshots
- manual collection with cooldown control
- automatic scheduled collection based on plan
- one daily email digest at 08:00
- subscription purchase through Epay

### 3.2 Out of scope

- public site directory operated by Argus
- team workspaces and multi-member collaboration
- usage-based scenario solver
- followed model list model
- alert rule model
- notification center model
- generic crawler support
- login-protected collection
- dynamic billing expression evaluation
- mobile app
- complex BI dashboards

## 4. User Identity and Login

### 4.1 Login method

The MVP does not use username + password registration.

It uses:

- email address
- one-time verification code

Flow:

1. user inputs email
2. system sends a login code
3. user inputs the code
4. on success, the system logs the user in or creates the account lazily if it does not exist yet

### 4.2 Session exclusivity

User sessions must be exclusive.

Meaning:

- if the same account logs in on another device or browser, the previous session becomes invalid
- only one active authenticated session is kept per account

### 4.3 Send-code rate limit

The send-code endpoint must be rate-limited with both email-based and IP-based controls.

Required limits:

- per email: at most 1 send per minute
- per email: at most 3 sends per 10 minutes
- per IP: at most 1 send per minute
- per IP: at most 3 sends per 10 minutes

The implementation should use a Django rate-limit library instead of ad hoc counters.

## 5. Monitored Site Model

### 5.1 MonitoredSite

Argus should replace the competitor concept with a personal monitored site concept.

`MonitoredSite` can be derived from the current `CompetitorSite` model by adding a foreign key to the owning user and changing semantics from public competitor to private watchlist entry.

Recommended fields:

- id
- user
- base_url
- name
- note
- icon_url
- usd_exchange_rate
- enabled
- last_fetch_at
- last_fetch_status
- last_error
- created_at
- updated_at

Constraints:

- uniqueness should be `(user, base_url)` instead of global `base_url`
- different users may monitor the same site independently

### 5.2 Input behavior

The user inputs only the site URL.

Argus must:

1. normalize it to canonical base URL
2. auto-discover metadata if possible
3. validate compatibility against public new-api endpoints
4. add it into that user's private watchlist

Argus itself does not curate a public list.

## 6. Pricing Collection

### 6.1 Data source

This MVP still only supports compatible public new-api pricing endpoints.

Primary source:

- `/api/pricing`

Optional discovery source:

- `/api/status`

### 6.2 Collection modes

The system must support:

- collection right after a site is added
- manual collection from the user interface
- automatic scheduled collection according to plan

### 6.3 Manual collection cooldown

Manual collection is allowed for all plans, but only once per hour per site.

Rule:

- a user may trigger one manual collection for the same site once every 60 minutes

### 6.4 Automatic collection frequency by plan

- Free: 1 automatic collection per day
- Pro: 3 automatic collections per day
- Plus: 3 automatic collections per day
- Max: 3 automatic collections per day by default in MVP

The exact execution windows can be fixed by the system and do not need to be user-configurable.

## 7. Daily Email Summary

### 7.1 Product rule

Argus does not implement separate FollowedModel, AlertRule, or Notification models in MVP.

Instead, it sends one daily summary email at 08:00.

### 7.2 Digest content

The email should summarize the monitored sites owned by that user.

Suggested content:

- site name and URL
- last successful collection time
- latest collection status
- snapshot count summary
- notable price changes since the previous digest window when available
- direct links into the Argus site detail/comparison pages

The goal is quick review, not a full BI report.

## 8. Static Comparison Rules

Comparison is always limited to the current user's monitored sites.

### 8.1 Token-based models

Compare using:

- converted input price per 1M
- converted output price per 1M

### 8.2 Request-based models

Compare using:

- converted request price

### 8.3 Dynamic billing

If `billing_mode` or `billing_expr` exists:

- store the snapshot
- mark it as dynamic
- exclude it from exact cheapest ranking in MVP

## 9. Plan and Pricing

### 9.1 Free

- up to 2 monitored sites
- 1 automatic collection per day
- manual collection allowed, 1 hour cooldown
- daily email digest at 08:00

### 9.2 Pro

- up to 10 monitored sites
- 3 automatic collections per day
- manual collection allowed, 1 hour cooldown
- daily email digest at 08:00
- price: 50 RMB per quarter
- price: 100 RMB per year

### 9.3 Plus

- up to 50 monitored sites
- 3 automatic collections per day
- manual collection allowed, 1 hour cooldown
- daily email digest at 08:00
- price: 50 RMB per month
- price: 300 RMB per year

### 9.4 Max

- up to 300 monitored sites
- 3 automatic collections per day in MVP
- manual collection allowed, 1 hour cooldown
- daily email digest at 08:00
- price: 1000 RMB per year

## 10. Payment

The MVP uses Epay as the payment provider.

Required behavior:

1. create subscription order
2. redirect or open Epay payment link
3. verify notify callback
4. verify return callback
5. activate or extend subscription after successful payment

The Python implementation should reference the existing new-api Epay flow conceptually.

If a mature Python SDK cannot be adopted confidently, Argus should implement a minimal internal Epay client sufficient for:

- purchase request signing
- callback verification
- trade status validation

## 11. Environment Variables

All email and payment configuration must come from `.env`.

### 11.1 Email config

Recommended variables:

- `ARGUS_EMAIL_BACKEND`
- `ARGUS_EMAIL_HOST`
- `ARGUS_EMAIL_PORT`
- `ARGUS_EMAIL_USE_TLS`
- `ARGUS_EMAIL_HOST_USER`
- `ARGUS_EMAIL_HOST_PASSWORD`
- `ARGUS_EMAIL_FROM`

### 11.2 Payment config

Recommended variables:

- `ARGUS_EPAY_ENABLED`
- `ARGUS_EPAY_URL`
- `ARGUS_EPAY_PID`
- `ARGUS_EPAY_KEY`
- `ARGUS_EPAY_NOTIFY_URL`
- `ARGUS_EPAY_RETURN_URL`

### 11.3 Auth/security config

Recommended variables:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `ARGUS_ALLOWED_HOSTS`
- `ARGUS_LOGIN_CODE_TTL_SECONDS`
- `ARGUS_LOGIN_CODE_RETENTION_SECONDS`, default `2592000` seconds / 30 days
- `ARGUS_LOGIN_CODE_COOLDOWN_SECONDS`
- `ARGUS_LOGIN_CODE_EMAIL_WINDOWS`, e.g. `[(600, 3), (86400, 10)]`
- `ARGUS_LOGIN_CODE_IP_WINDOWS`, e.g. `[(600, 10), (3600, 30)]`
- `ARGUS_LOGIN_CODE_MAX_ATTEMPTS`
- `ARGUS_SESSION_COOKIE_AGE_SECONDS`

## 12. Non-Functional Priorities

Priority order:

1. simple personal SaaS, not a platform
2. correctness of collected snapshots
3. stable login and payment flow
4. easy debugging and manual operation
5. only then UI polish

## 13. Acceptance Standard for MVP

The MVP is acceptable when:

1. a user can log in by email + code
2. send-code rate limits are enforced by email and IP
3. logging in on device B invalidates device A
4. a user can add at most the number of sites allowed by the current plan
5. each added site is collected and stored independently for that user
6. the comparison page compares only that user's monitored sites
7. manual collection respects the 1 hour cooldown
8. automatic collection runs according to plan frequency
9. a daily email digest is sent at 08:00 with links into Argus
10. Epay payment can activate or extend paid plans
11. the user-facing pages run with server-side rendering and only limited HTMX enhancement
12. the visual style is consistent with the dedicated frontend design language and avoids a default Django-admin look