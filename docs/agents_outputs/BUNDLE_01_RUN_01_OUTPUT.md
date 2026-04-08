# Bundle 01 — Run 01 Output: Admin Authentication and Role-Based Access

**Date:** 2026-04-09  
**Status:** Complete  
**Tests:** 193 passed (151 original + 42 new), 0 failed  
**Coverage:** 89%

---

## Summary

Implemented Bundle 01: separate admin authentication and role-based admin access for the CEMS election platform. Admin auth is now fully separated from student auth, with five defined roles and backend-enforced permissions on all lifecycle-critical actions.

---

## Current Code Inspected

Before implementation, the following codebase state was verified:

| File / Area | State |
|---|---|
| `apps/accounts/models.py` | Student model only; `is_admin` boolean flag |
| `apps/accounts/views.py` | Student login/logout only (student_id + birthdate) |
| `apps/accounts/decorators.py` | `login_required_student`, `admin_required` (checks `is_admin`) |
| `apps/elections/views.py` | Lifecycle views used `@login_required_student` + `@admin_required` |
| `apps/audit/models.py` | 6 event types, no admin-specific events |
| `config/urls.py` | Admin lifecycle endpoints existed but used student auth |
| `apps/frontend/views.py` | Admin panel checked student session |
| Tests | 150 passing tests, no admin auth separation tests |

---

## Implementation Approach

**Strategy: Django built-in `auth.User` + `AdminProfile` with role field**

- Used Django's default `auth.User` model for admin identity (username + password authentication)
- Created `AdminProfile` model (OneToOneField → User) with role choices field
- Admin auth uses `django.contrib.auth.authenticate()` / `login()` — completely separate from student session key (`authenticated_student_id`)
- New decorator stack: `admin_login_required` → `role_required(*roles)` → `electoral_board_head_required`
- Session separation: `request.user` for admin, `request.student` for student

**Why this approach:**
- No `AUTH_USER_MODEL` change needed → avoids migration breakage
- Django's password hashing + validation infrastructure is battle-tested
- `request.user` (Django auth) vs `request.session["authenticated_student_id"]` (custom) provides clean code separation
- Student session cannot inadvertently grant admin access, and vice versa

---

## Files Changed

### Models
| File | Change |
|---|---|
| `apps/accounts/models.py` | Added `AdminRole` choices and `AdminProfile` model |
| `apps/audit/models.py` | Added 3 event types: `ADMIN_LOGIN_ATTEMPT`, `ADMIN_LOGOUT`, `ADMIN_PERMISSION_DENIED` |

### Views
| File | Change |
|---|---|
| `apps/accounts/views.py` | Added `admin_login` and `admin_logout` views |
| `apps/elections/views.py` | Replaced `@login_required_student` + `@admin_required` with `@admin_login_required` + `@role_required(AdminRole.ELECTORAL_BOARD_HEAD)` on lifecycle endpoints |
| `apps/frontend/views.py` | Added `admin_login_page`, updated `admin_page` to check admin auth via Django User |

### Decorators
| File | Change |
|---|---|
| `apps/accounts/decorators.py` | Added `admin_login_required`, `role_required(*roles)`, `electoral_board_head_required`; kept legacy `admin_required` for backward compatibility |

### URLs
| File | Change |
|---|---|
| `apps/accounts/urls.py` | Added `admin_auth_urlpatterns` for admin login/logout |
| `config/urls.py` | Added `/api/admin/auth/` URL include |
| `apps/frontend/urls.py` | Added `/admin/login/` route |

### Admin
| File | Change |
|---|---|
| `apps/accounts/admin.py` | Registered `AdminProfile` model; added inline to User admin |

### Audit
| File | Change |
|---|---|
| `apps/audit/services.py` | Added logging branches for admin login, logout, and permission-denied events |

### Templates
| File | Change |
|---|---|
| `templates/frontend/admin_login.html` | **New** — Admin login page with separate UI |

### Management Commands
| File | Change |
|---|---|
| `apps/accounts/management/commands/create_admin.py` | **New** — CLI for creating admin users with roles |

### Test Infrastructure
| File | Change |
|---|---|
| `conftest.py` | Added `create_admin_user()` helper, `admin_client_for()` helper, admin fixtures |
| `tests/test_views.py` | Updated `TestAdminLifecycleViews` to use new admin auth; updated `TestAdminRequiredDecorator` |
| `tests/test_integration.py` | Updated integration flow to use admin auth; updated security test assertions |

---

## Migrations Added

| Migration | Description |
|---|---|
| `apps/accounts/migrations/0004_admin_profile_model.py` | Creates `AdminProfile` table |
| `apps/audit/migrations/0003_admin_audit_event_types.py` | Adds new event type choices to `AuditLog.event_type` |

---

## Tests Added/Updated

### New test file: `tests/test_admin_auth.py` (42 tests)

| Test Class | Tests | Covers |
|---|---|---|
| `TestAdminLogin` | 11 | Admin login success, failure, missing fields, invalid JSON, no profile, inactive profile, audit logging, method restriction, student credentials rejection |
| `TestAdminLogout` | 3 | Logout success, audit logging, unauthenticated logout |
| `TestAuthSeparation` | 3 | Student session → no admin access, admin session → no student access, legacy `is_admin` flag → no admin access |
| `TestRolePermissions` | 15 | EB Head can start/close/publish; Operator/Tally Watcher/Auditor/Tech Support cannot |
| `TestPermissionDeniedAudit` | 2 | Denied attempts are logged with actor and role |
| `TestAdminProfileModel` | 7 | Model properties, role choices, string representation |

### Updated tests

| File | Changes |
|---|---|
| `tests/test_views.py` | `TestAdminLifecycleViews` now uses EB Head user + operator user; tests operator blocked from start/close/publish; student auth returns 401 not 403 |
| `tests/test_integration.py` | Full workflow uses `admin_client_for(eb_head_user)` instead of student login; security test expects 401 for student auth |

---

## Manual Verification Steps

1. **Create admin user:**
   ```
   python manage.py create_admin --username eb_head --role electoral_board_head --display-name "VP Juan Dela Cruz"
   python manage.py create_admin --username operator1 --role electoral_board_operator --display-name "Operator One"
   ```

2. **Admin login via API:**
   ```
   POST /api/admin/auth/login/
   {"username": "eb_head", "password": "..."}
   ```
   → Expect 200 with role info

3. **Student login via API:**
   ```
   POST /api/auth/login/
   {"student_id": "2024-10015", "date_of_birth": "2000-08-04"}
   ```
   → Expect 200, but no admin access

4. **EB Head starts election:**
   ```
   POST /api/admin/elections/start/
   {"election_id": "..."}
   ```
   → Expect 200

5. **Operator tries to start election:**
   → Expect 403

6. **Student tries to start election:**
   → Expect 401

7. **Check audit log for admin events:**
   ```
   AuditLog.objects.filter(event_type__startswith='admin_')
   ```

8. **Visit admin login page:**
   `/admin/login/` → Should show admin login form

9. **Visit admin panel without admin auth:**
   `/admin-panel/` → Should redirect to `/admin/login/`

---

## Open Issues / Risks

| # | Issue | Severity | Notes |
|---|---|---|---|
| 1 | `is_admin` field on Student model is now legacy | Low | Kept for backward compatibility. Should be deprecated in a future bundle. |
| 2 | Admin login rate limit is stricter (5/min) than student (10/min) | Info | Intentional — admin accounts are higher-value targets. |
| 3 | Admin login template uses JS fetch — no server-side form handling | Low | Consistent with existing student login template pattern. |
| 4 | No password reset flow yet | Medium | Acceptable for Bundle 01; should be addressed in hardening phase. |
| 5 | Django admin site (`/admin/`) still uses Django's built-in login | Info | This is the infrastructure admin, not the election admin. Access should be restricted in production. |

---

## Recommended Next Prompt

```
Read these docs as authoritative:
- docs/SYSTEM_SOURCE_OF_TRUTH.md
- docs/KNOWN_DECISIONS_COMPACT.md
- docs/BUNDLE_02_CORE_ELECTION_DOMAIN_AND_VOTER_ROLL.md

Inspect the current codebase state (post-Bundle 01).
Implement Bundle 02: Core Election Domain and Voter Roll.

Do not change admin auth or role structure from Bundle 01.
Do not implement student ballot submission yet.
```
