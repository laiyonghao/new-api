# Argus Prototype IA Decision

## Status

- Adopted on 2026-05-07.
- This file records the current prototype information architecture decision.
- Follow this file for all later prototype edits unless a newer decision explicitly replaces it.

## Top-Level Product Areas

The prototype is now defined as four first-class areas:

1. Home
2. Watchlist
3. Pricing
4. Account

Interpretation:

- Home is the public landing page for brand, positioning, and user conversion.
- Watchlist is the main logged-in workspace and carries the core product capability.
- Pricing is a dedicated conversion area for paid plans.
- Account is the personal center for identity, session, and subscription maintenance.

## Page Ownership

Current prototype pages should be understood as belonging to these areas:

### Home

- index.html

### Watchlist

- sites.html
- comparison.html
- fetch-runs.html
- snapshots.html
- site-form.html
- custom-comparison.html

### Pricing

- billing.html

### Account

- account.html
- login.html

## Core Decision About Watchlist

"实时比价" is no longer treated as a separate top-level product area.

It belongs inside Watchlist.

That means:

- watchlist state, selected stations, compare scope, snapshots, and fetch history should be treated as one connected workspace;
- the user should feel they are staying inside the same tool context, not jumping across unrelated first-level pages;
- later implementation may use full page navigation, partial replacement, or htmx-style swapping, but the information architecture should already reflect one workspace.

## Watchlist Internal Menu Model

Watchlist should expose an internal switch model rather than pretending every function is a separate product.

Recommended internal menu set:

1. 站点
2. 已选比价
3. 采集记录
4. 价格底稿
5. 规则 / 设置

Notes:

- "Rules / Settings" is not fully represented yet in the current prototype, but it should exist in the architecture because exchange rate, grouping, and multiplier rules are part of the user task model.
- custom-comparison should be treated as a temporary compare variant, not a separate top-level destination.
- site-form should be treated as a fallback or detail view inside Watchlist, not a first-class area.

## Watchlist Shared Shell Contract

All first-class Watchlist pages should reuse one compact shared shell.

The shell exists to keep the user in one workspace mental model and to avoid each page reinventing its own header logic.

Required shell elements:

1. Breadcrumb: 首页 / Watchlist / 当前页
2. Local navigation row: 站点 / 已选比价 / 采集记录 / 价格底稿 / 规则 / 设置
3. Three compact summary cards near the top of the page

Summary-card intent:

- card 1 explains the current page role;
- card 2 tells the user what object, scope, or selection they are looking at;
- card 3 explains current mode, status, or operational guidance.

Constraints:

- keep the shell compact so data stays close to the top of the page;
- do not reintroduce a heavy admin sidebar pattern;
- do not use a marketing-style hero on Watchlist pages;
- if a page belongs to Watchlist, the page should look like it belongs to the same workspace within the first screen.

## Concrete Watchlist Page Roles

The current prototype Watchlist pages should be interpreted like this:

- sites.html: the canonical station page and the baseline implementation of the shared shell.
- comparison.html: the normal selected-compare page inside Watchlist, not a top-level product destination.
- fetch-runs.html: the run-monitoring page for freshness, failures, and manual queue actions.
- snapshots.html: the price provenance page for normalized model mapping, billing status, and evidence review.
- custom-comparison.html: a transitional Watchlist view only, used for old custom-compare entry points or temporary compare params.
- site-form.html: a fallback/detail page only, used when the station modal is not enough for long-form editing, failure recovery, or full-context review.

Interpretation rules:

- sites.html, comparison.html, fetch-runs.html, and snapshots.html are normal internal destinations.
- custom-comparison.html should never be treated as the default compare experience.
- site-form.html should never be treated as the default add/edit flow.
- normal station add/edit work should stay centered on modal interactions launched from the station page.

## Navigation Rules

### Global Navigation

The first-level navigation should represent only these four areas:

1. Home
2. Watchlist
3. Pricing
4. Account

### Watchlist Navigation

Inside Watchlist, use a shared local navigation component.

It does not need to be a heavy admin sidebar.

It can be:

- a shared row of buttons;
- a tab-like bar;
- or a compact switcher reused across Watchlist pages.

The important rule is consistency of mental model, not a specific widget style.

## Interaction Rules

To avoid drifting back into scattered standalone tools, use these interaction rules:

1. Home is the only page allowed to spend large vertical space on a hero section.
2. All secondary pages should surface data, controls, or operational context near the top.
3. Login and station add/edit flows should prefer dialogs or lightweight overlays.
4. Standalone pages such as login.html or site-form.html are fallback surfaces, not the preferred daily path.
5. When a task can stay inside Watchlist without losing context, keep it inside Watchlist.

## Directory Strategy

Target prototype directory structure should reflect the four areas.

Keep Home at the root because it is the single public landing page.

Everything else should eventually be grouped by area.

Practical interpretation:

- the current root-level tool pages are transitional;
- later prototype HTML files should be moved under area-based directories;
- during migration, short-term coexistence is acceptable, but old root-level pages should no longer drive the product mental model.

## Migration Principles

To avoid context drift and sloppy rewrites, use these rules for future prototype work:

1. Edit one file at a time.
2. After each file edit, do one narrow verification step before touching the next file.
3. Prefer reshaping one page cleanly over partially touching many pages.
4. Treat this IA file as the source of truth for deciding where a page belongs.
5. When a page conflicts with this structure, fix the structure first, not just the copy.
6. If a Watchlist page loses the shared shell, restore the shell before polishing local copy.
7. If a fallback page starts reading like a primary destination, rewrite its positioning immediately.
8. When the prototype changes the role of a page, update this file in the same pass.

## Recommended Order For Future Changes

1. Align top-level navigation wording and destinations to the four areas.
2. Establish Watchlist as a single workspace concept.
3. Move or recreate Watchlist pages under a Watchlist area structure.
4. Keep Pricing and Account as clean, separate conversion and maintenance areas.
5. Remove leftover first-level mental models that still present compare as an independent product area.

## Decision Summary

The product is not a set of unrelated pages.

It is:

- one public landing page,
- one main logged-in workspace,
- one pricing area,
- and one personal center.

All future prototype edits should reinforce that model.