---
name: responsive-audit
description: Audit and fix the mobile/tablet responsiveness of the Ochiq Kurs LMS by rendering every page at narrow widths in both themes with Playwright, detecting horizontal overflow programmatically, then fixing CSS/templates. Use when changing front-end layout/CSS, adding pages, or when asked to check that pages work on mobile / are responsive / have no overflow.
---

# Responsive audit

Renders every user-facing page at phone/tablet widths in light **and** dark themes
using Playwright + the system Chrome, flags any horizontal overflow (and the
element causing it), screenshots each render, then guides the fixes. This is the
executable version of the "render the UI to audit it" rule — static CSS reading
misses theme/overflow/hover tells.

## When to use
- Any front-end layout or CSS change (verify it didn't break narrow screens).
- Adding/changing a page or template.
- A request like "is the site responsive", "check mobile", "components cut off".

## Prerequisites (one-time)
- `cd .claude/skills/responsive-audit && npm i playwright` (uses `channel: 'chrome'`,
  so no Chromium download — system Google Chrome must be installed).
- A local DB with content (the dev `.env` points at a localhost copy of prod data).

## Workflow

1. **Start the dev server** on a free port:
   ```bash
   venv/bin/python manage.py runserver 127.0.0.1:8009 --noreload &
   ```

2. **Generate sessions + URL map** (no data is mutated — sessions only):
   ```bash
   mkdir -p /tmp/respaudit && \
   venv/bin/python manage.py shell < .claude/skills/responsive-audit/setup.py \
     | grep AUDITJSON | sed 's/AUDITJSON//' > /tmp/respaudit/audit.json
   ```
   `setup.py` picks representative slugs from existing data (course/module/lesson,
   category, quiz attempt, certificate, and — if present — an article lesson,
   learning path, instructor-linked course) and creates login sessions for a
   regular user, a staff user, and the certificate owner. Pages whose data is
   missing are simply omitted (it prints which).

   - **Optional full coverage:** if article lessons / learning paths / an
     instructor FK don't exist, the audit skips those pages. To cover them,
     create minimal fixtures in the **local** DB first, then **delete them after**
     (they are a copy of prod data — never leave test rows). See the commented
     `make_fixtures()` block in `setup.py`.

3. **Render + detect overflow** (23 pages × 375/414/768px × light/dark = 138 renders):
   ```bash
   cd .claude/skills/responsive-audit && \
   AUDIT_JSON=/tmp/respaudit/audit.json OUT_DIR=/tmp/respaudit/shots \
   node audit.js before
   ```
   It prints every `OVERFLOW <page> <theme> <width> = +Npx :: <offenders>` line,
   a summary count, screenshots to `/tmp/respaudit/shots/before/`, and a machine
   results file `results-before.json`. **Empty offenders usually means the culprit
   is `position:fixed`** (the detector skips fixed) — debug it directly (see below).

4. **Visually review** the complex pages even when overflow is 0 — overflow ≠
   "all components visible & usable". Read the screenshots for: lesson detail
   (video/article/quiz), profile/dashboard, admin panel, course detail,
   certificate, leaderboard, login. Check both themes.

5. **Fix**, then re-render with a new label (`node audit.js after`) and compare.
   Iterate until `0 with overflow`.

6. **Verify**: `venv/bin/python manage.py test` (CSS/template-only changes
   should keep all tests green), then stop the server and clean up any fixtures.

## Debugging a single offender
When `OVERFLOW` lists no offender (fixed element) or you need the exact node:
```bash
cd .claude/skills/responsive-audit && node debug.js <url-path>
# e.g. node debug.js /malaka/<course>/<module>/<lesson>/
```
It prints the widest elements crossing the right edge (incl. fixed), with class,
position and width — usually enough to name the culprit.

## Fix conventions (match the existing CSS in `static/css/style.css`)
- Prefer **targeted `@media` rules**; reuse the existing breakpoints
  (480/600/640/720/768/900/960/1024) and `:root` tokens (`--container`,
  `--container-wide`, `--nav-h`). Don't invent a new breakpoint system.
- **CSS-grid blowout** (a `1fr` track grown past the viewport by a wide child):
  use `grid-template-columns: minmax(0, 1fr)` and add `min-width: 0` to the grid
  children. The `auto` minimum of a plain `1fr` = min-content, which wide
  iframes/`<pre>`/`<table>`/nowrap text will blow out.
- **Long unbreakable text** (titles, codes, names): `overflow-wrap: anywhere`
  (and `white-space: normal` if it was `nowrap`).
- **Wide tables / code**: wrap in an `overflow-x: auto` container (markdown
  tables: `display:block; overflow-x:auto`).
- **Button/tab rows that don't fit**: `flex-wrap: wrap`, or horizontal scroll
  (`overflow-x:auto` + `flex-shrink:0` on items) for tab bars.
- **`@media` ordering gotcha**: media queries add **no** specificity. A
  same-specificity rule placed *later* in the file beats your `@media` override.
  Put mobile overrides **after** the base rule they target (this bit the
  certificate heading once).
- Hiding desktop-only chrome: a `.parent .nav-only-desktop` rule only hides
  matches *inside* `.parent`. If the class is used elsewhere too, scope the hide
  rule to the class itself.

## Notes
- Theme is forced via `localStorage.theme` (an `addInitScript` before load), which
  is how `static/js/ui.js` reads it — not a cookie.
- Static files serve live in `DEBUG=True`; no `collectstatic` needed between edits.
- `/tmp/respaudit/` is scratch space — safe to delete. `node_modules/` here is
  git-ignored; keep it out of commits.
