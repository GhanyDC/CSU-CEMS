# ADMIN_LOGIN_ROUTE_FIX_RUN_01_OUTPUT

**Date:** 2026-04-09
**Scope:** Fix `/admin/login/` shadowed by Django admin; move custom election-admin login to `/election-admin/login/`

---

## 1. Summary of the Bug

Visiting `/admin/login/` showed Django's built-in "Django administration" login page instead of the CEMS custom election-admin login UI. This happened because Django's built-in admin is mounted at `path("admin/", ...)`, which makes `/admin/login/` part of Django's own URL space. Any custom path placed outside `path("admin/", ...)` that tried to intercept `/admin/login/` would lose to Django's admin prefix match.

This caused confusion for election officers trying to log in via the custom `eb_head`/`operator1` credentials, because those admin accounts are not superusers and cannot authenticate via Django's built-in admin form.

Additionally, when `apps/frontend/urls.py` was partially updated (presumably by a formatter or manual edit), it introduced a **syntax error** (missing comma) and a **URL name mismatch** (URL named `"admin_login"` with underscore while `views.py` redirects using `"frontend:admin-login"` with a hyphen), which would have caused a `NoReverseMatch` runtime error on any unauthenticated admin-panel access.

---

## 2. Root Cause Found

Three compounding issues:

| # | Issue | Location |
|---|-------|----------|
| 1 | Django's `path("admin/", admin.site.urls)` owns the `/admin/` prefix. Any path placed in `frontend/urls.py` as `/admin/login/` is unreachable — Django admin intercepts it first. | `config/urls.py` |
| 2 | `apps/frontend/urls.py` was partially updated to `/election-admin/login/` but had a missing comma (syntax error) and wrong `name="admin_login"` (underscore) that didn't match the view's `redirect("frontend:admin-login")` (hyphen). | `apps/frontend/urls.py` |
| 3 | `templates/frontend/admin_panel.html` hardcoded `'/admin/login/'` in two JS redirect calls (unauthenticated guard + logout button), sending users to Django admin instead of the CEMS login page. | `templates/frontend/admin_panel.html` |

---

## 3. Fix Approach Chosen

**Clean path change** — move the custom election-admin login to a route that cannot conflict with Django's admin prefix. The chosen path is:

```
/election-admin/login/
```

This is:
- Semantically clear (not ambiguous with `/admin/`)
- Never going to conflict with Django's `path("admin/", ...)` prefix
- Consistent with `/admin-panel/` (also not under `/admin/`)

Django's built-in `/admin/` is preserved as-is for infrastructure/superuser use. No merged auth, no path-ordering hacks.

---

## 4. Files Changed

| File | Change |
|------|--------|
| `apps/frontend/urls.py` | Fixed missing comma; corrected URL name from `"admin_login"` (underscore) to `"admin-login"` (hyphen) to match `views.py`'s `redirect("frontend:admin-login")` |
| `templates/frontend/admin_panel.html` | Changed 2 JS hardcoded redirects: `'/admin/login/'` → `'/election-admin/login/'` (unauthenticated guard on init, logout button handler) |
| `tests/test_admin_setup.py` | Updated existing assertion: `"/admin/login/"` → `"/election-admin/login/"`; added 2 new regression tests |
| `MANUAL_TESTING_CHECKLIST_LATEST.md` | Updated C1 manual test step URL |

No models, migrations, auth logic, or frozen election rules were changed.

---

## 5. Tests Added / Updated

| Test | File | Type |
|------|------|------|
| `test_admin_page_requires_auth` — assertion updated to `/election-admin/login/` | `tests/test_admin_setup.py` | Updated |
| `test_election_admin_login_page_loads` — GET `/election-admin/login/` returns 200 with custom CEMS admin form (not Django admin) | `tests/test_admin_setup.py` | New |
| `test_django_admin_still_independent` — GET `/admin/` returns 200 or 302 and does NOT render the CEMS admin template | `tests/test_admin_setup.py` | New |

---

## 6. New Correct Election-Admin Login URL

```
/election-admin/login/
```

Full dev URL: `http://localhost:8000/election-admin/login/`

Django's built-in admin remains at: `http://localhost:8000/admin/`

---

## 7. Manual Verification Steps

1. Start the dev server: `python manage.py runserver --settings=config.settings.local`
2. Visit `http://localhost:8000/election-admin/login/` — should show the CEMS "Election Administration Portal" login form (amber/warning colour scheme), not the Django admin grey form
3. Log in as `eb_head` / `pilot_admin_pass` — should redirect to `/admin-panel/`
4. Click Logout — should redirect back to `/election-admin/login/`
5. Visit `http://localhost:8000/admin-panel/` while logged out — should redirect to `/election-admin/login/`
6. Visit `http://localhost:8000/admin/` — should still show the Django administration login (separate, unchanged)
7. Visit `http://localhost:8000/admin/login/` — should show Django's built-in admin login (confirming no conflict)

---

## 8. Test Results

| Suite | Result |
|-------|--------|
| `python -m pytest tests/ -q` | **357 passed** in 6.34s (355 before + 2 new) |

---

## 9. Remaining Risks / Follow-ups

| Item | Severity | Notes |
|------|----------|-------|
| Old URL bookmarks / docs | Low | `docs/agents_outputs/BUNDLE_01_RUN_01_OUTPUT.md` and `BUNDLE_03_RUN_01_OUTPUT.md` still mention `/admin/login/`. These are archived run outputs — update only if actively used as references. |
| `run_pilot_test.py` | None | Pilot test uses the API endpoint `/api/admin/auth/login/` directly (not the UI page URL), so it is unaffected. |
| Django admin access for superusers | None | `/admin/` remains fully operational for infrastructure use. Election officers with non-superuser accounts cannot reach Django admin, which is correct behavior. |

---

## 10. Recommended Next Prompt

> Open a browser and do a manual round-trip: visit `http://localhost:8000/election-admin/login/`, log in as `eb_head`, create a new campus election from the admin panel, add candidates, generate the voter roll, and start the election. Then switch to a student account and verify the dashboard shows the active election and allows voting. Report any template rendering errors, broken JS, or API failures observed.
