# Bundle 01 — Admin Authentication and Role-Based Access

Status: Implementation bundle  
Recommended model use: **Plan once if needed, then Agent mode**

---

## 1. Purpose
This bundle separates admin authority from student voter authentication and introduces role-based access control for election officers.

This bundle should be implemented before major election workflows, because later admin features depend on secure identity separation.

---

## 2. Why this bundle exists
Current voter authentication is student-facing and is based on student identity data. That is not sufficient for privileged election authority roles.

This bundle establishes:
- separate admin login
- named admin accounts
- role-based permissions
- restriction of critical actions to the Electoral Board Head only

---

## 3. Scope of this bundle
### In scope
- separate admin authentication flow
- admin account model or admin-role extension strategy
- role definitions and permission checks
- protection of sensitive election routes/actions
- admin session handling
- audit logging for admin login and critical role-based actions

### Out of scope
- full election setup screens
- voter-roll imports
- student ballot submission
- final results UI

---

## 4. Frozen rules for this bundle
- Admin authentication must be separate from student authentication.
- Admins must not log in using only student ID + birthdate.
- The Vice President serves as the Electoral Board Head role.
- Only the Electoral Board Head role may:
  - finalize voter rolls
  - start elections
  - close elections
  - publish results
- Operators cannot perform those actions.
- Tally Watchers, Auditors, and Technical Support are read-only or limited-function roles.
- No shared admin account should be used.

---

## 5. Recommended implementation direction
### Admin identity model
Use one of these patterns:
1. Dedicated `AdminUser` model tied to Django auth
2. Django `User` plus election-admin profile/role model

Preferred outcome:
- a clear admin-only authentication flow
- named admin accounts
- explicit roles
- auditable actions per person

### Role set
Required roles:
- Electoral Board Head
- Electoral Board Operator
- Tally Watcher
- Auditor
- Technical Support

### Permission strategy
Protect at both levels:
- route/view access
- action/service-level permission checks

Do not rely only on UI hiding.

---

## 6. Deliverables
Expected outputs from implementation:
- admin auth model design implemented
- admin login route and form/view
- admin logout route
- role storage and permission checks
- permission guards for protected actions
- audit logging for admin logins and restricted-action attempts
- initial admin account seeding or management approach documented

---

## 7. Acceptance criteria
This bundle is complete when:
- student login and admin login are fully separate
- admin accounts authenticate with username/email + password
- unauthorized users cannot access admin pages
- only Electoral Board Head can finalize voter rolls, start, close, and publish
- Operators are blocked from those actions
- read-only roles cannot mutate election data
- audit logs capture admin logins and permission-denied attempts

---

## 8. Suggested files and areas likely affected
This is guidance, not a strict file list.

Likely affected areas:
- accounts/admin-auth app or equivalent
- models for admin roles
- auth views/routes/templates or API endpoints
- middleware/decorators/permission utilities
- admin dashboard entry logic
- audit logging services
- tests for role access

---

## 9. Risks to avoid
- reusing student login for admin authority
- hidden permission logic only in templates
- shared admin credentials
- unclear separation between technical support and election authority
- allowing Operators to start/close/publish by mistake

---

## 10. Manual test checklist
- admin can log in with admin credentials
- student credentials cannot access admin login flow
- student account cannot perform admin actions
- Operator can access operator-allowed pages but cannot start/close/publish
- Electoral Board Head can access VP-only actions
- Tally Watcher cannot edit data
- Auditor cannot edit data
- Technical Support cannot access election-control actions
- denied attempts are logged

---

## 11. Compact planning prompt template
Use this only if a planning pass is needed.

```text
Read these docs as authoritative:
- docs/SYSTEM_SOURCE_OF_TRUTH.md
- docs/KNOWN_DECISIONS_COMPACT.md
- docs/BUNDLE_01_ADMIN_AUTH_AND_ROLES.md

Task: Plan Bundle 01 only.

Do not redesign frozen election rules.
Do not work on student voting yet.
Do not work on election setup UI yet.

Produce:
1. proposed model/auth approach
2. affected files/modules
3. migrations needed
4. permission strategy
5. risks
6. acceptance checklist
7. tests to add
```

---

## 12. Compact agent prompt template
```text
Read these docs as authoritative:
- docs/SYSTEM_SOURCE_OF_TRUTH.md
- docs/KNOWN_DECISIONS_COMPACT.md
- docs/BUNDLE_01_ADMIN_AUTH_AND_ROLES.md

Implement Bundle 01 only.

Rules:
- keep admin auth separate from student auth
- enforce VP-only finalization/start/close/publish
- use named admin accounts
- add tests for role restrictions
- do not implement later bundles yet

Before coding, briefly list the files you plan to modify.
After coding, summarize:
- files changed
- migrations added
- tests added
- manual checks to run
```

