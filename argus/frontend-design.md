# Argus Frontend Design Language

## 1. Intent

Argus should feel familiar to users who already spend time with modern AI products, especially calm, editorial product sites and dashboards with warm neutrals and restrained accents.

The goal is not to copy any specific site.

The goal is to recreate the same emotional qualities:

- calm
- trustworthy
- human
- focused
- quietly premium

Argus should avoid:

- neon SaaS gradients
- high-saturation tech blue as the primary accent
- cramped admin-table density everywhere
- loud motion or decorative clutter

## 2. Reference Translation

The chosen visual reference suggests a Claude-adjacent language with these transferable traits:

- warm paper-like page background
- strong heading presence with editorial rhythm
- large rounded surfaces with low-contrast borders
- restrained warm accent color for primary actions and key highlights
- generous whitespace and content blocks that breathe

Argus should translate those traits into its own UI system rather than reproducing the reference page structure, assets, or copy.

## 3. Audience Lens

Primary users are AI relay buyers and heavy AI tool users.

They should feel:

- this product is built by people who understand AI workflow friction
- the product is clear enough to trust with daily monitoring
- the interface is more product-like than spreadsheet-like

## 4. Color Tokens

Use clean grayscale neutrals with an energetic orange accent, matching the TokenCloud reference.

### 4.1 Base colors

- page background: `#ffffff` or `bg-slate-50`
- surface: `#ffffff` (`bg-white`)
- border: `border-gray-200`
- secondary background: `bg-slate-100`

### 4.2 Text colors

- text primary: `text-slate-900`
- text secondary: `text-slate-600`
- text muted: `text-slate-400`

### 4.3 Accent colors

- accent primary: `bg-orange-600`
- accent primary hover: `bg-orange-500`
- accent soft: `bg-orange-50`
- text accent: `text-orange-600`

### 4.4 Semantic colors

- success bg: `#e6f1e8`
- success text: `#2f6a3d`
- warning bg: `#f7ead3`
- warning text: `#8a5a1f`
- danger bg: `#f6ded8`
- danger text: `#8a3d2d`
- info bg: `#e8efe9`
- info text: `#35574a`

## 5. Typography

Use a mixed system:

- headings: serif-forward or editorial-feeling family
- body: clean sans-serif with soft shapes
- numeric data: same sans-serif, tabular numerals when available

Recommended practical stack for MVP without external font hosting:

- heading: `Iowan Old Style`, `Palatino Linotype`, `Book Antiqua`, `Georgia`, serif
- body: `ui-sans-serif`, `system-ui`, `-apple-system`, `BlinkMacSystemFont`, `Segoe UI`, sans-serif

Scale guidance:

- hero title: 52 to 64 px desktop, 36 to 42 px mobile
- section title: 30 to 38 px desktop, 24 to 30 px mobile
- page title: 28 to 34 px
- card title: 18 to 22 px
- body: 15 to 17 px
- dense metadata: 13 to 14 px

## 6. Layout Principles

- content should sit in a centered shell with large horizontal breathing room
- avoid narrow, over-compressed dashboard columns
- use 24 to 32 px padding inside major cards on desktop
- on mobile, keep 16 to 20 px padding and stack blocks aggressively
- prefer 1 to 3 strong content regions per screen rather than many small widgets

Recommended shell widths:

- marketing pages: 1180 to 1240 px
- application pages: 1200 to 1320 px

## 7. Component Rules

### 7.1 Cards

- radius: 24 px for major surfaces
- radius: 18 px for secondary surfaces
- border: 1 px solid low-contrast warm border
- shadow: soft, diffuse, low contrast
- cards should feel tactile but not elevated like mobile material cards

### 7.2 Buttons

- primary button uses accent fill with dark warm text or off-white text depending on contrast
- secondary button uses surface fill with visible border
- ghost button is acceptable for low-priority inline actions
- button radius should be pill-like or softly rounded, never sharp

### 7.3 Forms

- inputs should be large, calm, and readable
- avoid thin gray input borders on pure white backgrounds
- labels remain visible above controls, not only placeholders
- helper text and error text should be explicit and human-readable

### 7.4 Tables and lists

- prefer cardified rows when information density is moderate
- use tables only where comparison truly benefits from row alignment
- if tables are used, soften them with row spacing, tinted headers, and generous padding

### 7.5 Status chips

- use soft background fills and readable text
- rounded full-pill shapes are preferred
- color should indicate state without dominating the page

## 8. Motion and Interaction

Motion should be minimal.

Allowed:

- hover elevation shift within 2 to 4 px feel
- opacity fade or slight translate on section reveal
- loading shimmer or subtle pulse for HTMX replacement areas

Avoid:

- parallax
- bouncing counters
- flashy gradients or rotating ornaments

## 9. HTMX UX Guidance

HTMX should preserve page calmness.

Rules:

- partial refresh should be visually obvious but not jarring
- always define loading, empty, and error states for HTMX target regions
- use inline success and failure messages near the form or panel that triggered the action
- avoid replacing the entire page when only one section changed

Recommended high-value HTMX interactions:

- send login code and return inline countdown or status
- create monitored site and refresh the site list section
- trigger manual fetch and refresh only that site card
- change comparison filters and refresh only the result area
- create billing order and replace only the checkout action region

## 10. Page-Specific Direction

### 10.1 Landing page

- large editorial hero
- one clear promise
- 3 to 4 benefit cards
- product-preview strip for comparison monitoring feel
- restrained CTA group

### 10.2 Login page

- quiet and welcoming, not clinical
- code send flow should feel lightweight and safe
- include clear rate-limit expectations in helper text

### 10.3 Monitored site list

- treat sites as tracked assets, not database rows
- each site row or card should show health, last fetch time, and next useful action immediately

### 10.4 Comparison page

- keep the result area highly legible
- cheapest values should be easy to scan without looking like a trading terminal
- filters belong above results in a calm control panel

### 10.5 Billing page

- plan cards should feel straightforward and transparent
- avoid dark-pattern urgency language

### 10.6 Account page

- security, email, session status, and digest preferences should appear trustworthy and stable

## 11. Prototype Scope

The first static prototype should cover:

- landing page
- login page
- monitored site list page
- comparison page
- billing page
- account page

All prototype pages should share the same tokens, spacing, and shell so implementation can be translated into Django templates with minimal churn.