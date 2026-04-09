# Security Findings — Run 01

**Date:** 2026-04-09  
**Scope:** Full CEMS codebase security review (auth, sessions, CSRF, role enforcement, ballot integrity, data isolation)

---

## Findings by Severity

### CRITICAL

#### SF-01: Admin Login JavaScript Block Silently Dropped

**Status: FIXED**

- **Location:** `templates/frontend/admin_login.html` line 44
- **Description:** The admin login template used `{% block extra_js %}` to inject its JavaScript form handler. The base template (`base.html`) defines `{% block extra_scripts %}` — not `{% block extra_js %}`. Django's template inheritance silently ignores blocks that don't exist in the parent template. The form rendered correctly but the submit handler was never attached.
- **Impact:** Custom admin login completely non-functional. Clicking "Admin Sign In" either did nothing (JS not loaded) or caused a raw HTML form POST to the API endpoint which returned JSON instead of a redirect.
- **Fix:** Changed block name from `extra_js` to `extra_scripts` in `admin_login.html`.
- **Test:** `TestAdminLoginTemplateRegression.test_admin_login_page_contains_js`

---

### MEDIUM

#### SF-02: CSRF Token Missing from Login Forms (Production Failure)

**Status: FIXED**

- **Location:** `templates/frontend/admin_login.html`, `templates/frontend/login.html`
- **Description:** Both login forms used JavaScript `fetch()` to submit credentials. The JS code retrieves the CSRF token from a hidden field (`[name=csrfmiddlewaretoken]`) first, then falls back to reading the CSRF cookie via `document.cookie`. In `config/settings/base.py`, `CSRF_COOKIE_HTTPONLY = True` — this means JavaScript **cannot** read the cookie. Without a `{% csrf_token %}` hidden field, the CSRF token would be `null`, and all login requests would receive 403 Forbidden in production.
- **Impact:** Both admin and student login would fail in any environment using production settings.
- **Fix:** Added `{% csrf_token %}` inside both `<form>` elements.
- **Test:** `TestAdminLoginTemplateRegression.test_admin_login_has_csrf_token`

#### SF-03: Session Cross-Contamination Between Auth Systems

**Status: FIXED**

- **Location:** `apps/accounts/views.py` — `admin_login()` and `student_login()`
- **Description:** CEMS uses two independent auth systems sharing one Django session:
  - **Student auth:** Session keys `authenticated_student_id`, `student_id`
  - **Admin auth:** Django's built-in `auth.login()` / `auth.logout()` via `request.user`
  
  When an admin logged in, any existing student session keys were preserved. When a student logged in, any existing Django auth session was preserved. This allowed a single browser session to carry both admin and student identity simultaneously.
- **Impact:** Authorization confusion. A user could be simultaneously recognized as an admin and a student, potentially accessing student-only or admin-only endpoints with combined privileges.
- **Fix:** 
  - `admin_login()` now pops `authenticated_student_id` and `student_id` from the session after `login()`.
  - `student_login()` now calls `logout(request)` before setting student session keys.
- **Test:** `TestSessionIsolation.test_admin_login_clears_student_session`, `TestSessionIsolation.test_student_login_clears_admin_session`

---

### LOW

#### SF-04: Logout Endpoints Missing CSRF Protection

**Status: FIXED**

- **Location:** `apps/accounts/views.py` — `student_logout()`, `admin_logout()`
- **Description:** Both logout endpoints accepted POST but lacked `@csrf_protect`. An attacker could craft a cross-site form that forces a victim's browser to POST to the logout endpoint, logging them out without consent.
- **Impact:** Forced logout (denial of service to individual user). Low severity since it doesn't compromise data, but annoying and violates defense-in-depth.
- **Fix:** Added `@csrf_protect` decorator to both `student_logout` and `admin_logout`.
- **Test:** `TestAuthFlowEndToEnd.test_admin_login_logout_roundtrip`, `TestAuthFlowEndToEnd.test_student_login_logout_roundtrip`

---

## Open / Not Fixed (Acknowledged Risks)

### NFx-01: No Rate Limiting on Login Endpoints in Production Configuration

**Severity: Medium | Status: ACKNOWLEDGED**

- **Description:** Rate limiting exists in `base.py` (`RATE_LIMIT_WINDOW`, `RATE_LIMIT_MAX_ATTEMPTS`) and is enforced in `student_login` and `admin_login` via `apps.accounts.utils.check_rate_limit()`. However, there is no centralized rate-limiting middleware (e.g., `django-ratelimit` or `django-axes`), and the implementation uses a simple cache-based counter.
- **Risk:** Sophisticated distributed brute-force attacks could bypass IP-based limiting. No account lockout after N failures.
- **Recommendation:** Consider `django-axes` for persistent login attempt tracking and lockout.

### NFx-02: No Password Complexity Enforcement

**Severity: Low | Status: ACKNOWLEDGED**

- **Description:** Admin accounts created via `create_admin` management command or `generate_pilot_data` do not enforce password validators. The `AUTH_PASSWORD_VALIDATORS` in `base.py` applies only to Django's `createsuperuser` and `changepassword` management commands by default.
- **Risk:** Weak admin passwords in production.
- **Recommendation:** Call `validate_password()` explicitly in `create_admin` command and in any future admin password change flow.

### NFx-03: CSV Upload Injection Not Fully Mitigated

**Severity: Low | Status: ACKNOWLEDGED**

- **Description:** The voter roll CSV upload in `admin_views.py` processes CSV files server-side. While the data is used in database ORM operations (not string-concatenated SQL), there is no validation against excessively large files or CSV formula injection (`=CMD(...)` cells).
- **Risk:** Denial of service via very large CSV; formula injection if CSV data is later exported and opened in Excel.
- **Recommendation:** Add file size limit, row count limit, and sanitize cell values that begin with `=`, `+`, `-`, `@`.

### NFx-04: No Session Timeout Configuration

**Severity: Low | Status: ACKNOWLEDGED**

- **Description:** Django's default `SESSION_COOKIE_AGE` is 2 weeks. For an election system, sessions should expire more quickly (e.g., 30 minutes to 2 hours).
- **Risk:** Shared/public computer scenario — student walks away, next user accesses their session.
- **Recommendation:** Set `SESSION_COOKIE_AGE = 1800` (30 min) or implement idle-timeout middleware.

### NFx-05: Concurrency Safety Depends on PostgreSQL

**Severity: Medium | Status: ACKNOWLEDGED**

- **Description:** `BallotService.cast_ballot()` uses `select_for_update()` for atomic ballot creation. This is correctly implemented but only effective with PostgreSQL. SQLite (used in tests) silently ignores `select_for_update()`.
- **Risk:** Race condition in ballot creation is possible under SQLite but not under PostgreSQL.
- **Recommendation:** Run a dedicated concurrency test suite against PostgreSQL.

---

## Security Controls Verified as Correct

| Control | Status |
|---------|--------|
| Admin role enforcement via `@role_required` / `@admin_login_required` / `@electoral_board_head_required` decorators | **Correct** |
| Technical Support role excluded from all operational endpoints | **Correct** |
| Ballot hashing uses `hashlib.sha256` with per-election salt | **Correct** |
| One-ballot-per-voter enforced via `UNIQUE CONSTRAINT(election, voter_hash)` | **Correct** |
| Voter roll finalization freezes EligibleVoter set | **Correct** |
| Election lifecycle transitions validated in `ElectionLifecycleService` | **Correct** |
| Cross-college isolation enforced in ballot/voting views | **Correct** |
| Audit logging for login, logout, vote, lifecycle changes | **Correct** |
| CSRF middleware enabled globally | **Correct** |
| `SECURE_BROWSER_XSS_FILTER`, `X_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS` all set | **Correct** |
| `SESSION_COOKIE_HTTPONLY = True` | **Correct** |
| `CSRF_COOKIE_HTTPONLY = True` (production) | **Correct** |
| Password hashing uses Django defaults (PBKDF2 in base, MD5 only in test) | **Correct** |

---

## Areas Needing Future Hardening

1. **Rate limiting:** Replace simple cache counter with `django-axes` or `django-defender`.
2. **CSP headers:** Add `Content-Security-Policy` header to prevent XSS. Currently not set.
3. **CSV upload:** Add file size, row count, and cell content sanitization.
4. **Session management:** Configure session timeout and idle timeout.
5. **Admin password flow:** Implement password change and reset with complexity validation.
6. **Concurrency testing:** Run ballot-casting concurrency tests against PostgreSQL.
7. **Subresource Integrity (SRI):** Bootstrap CSS/JS loaded from CDN without SRI hashes.
