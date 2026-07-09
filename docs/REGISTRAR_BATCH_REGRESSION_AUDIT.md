# Registrar-Batch Registration Regression Audit

Date: 2026-07-09  
Environment: local Docker app at `http://localhost:8000`, Postgres mapped to host port `5434`

## Verdict

PASS. The registrar-batch registration workflow passed automated regression checks, live endpoint smoke checks, and an end-to-end registrar-batch workflow test.

No blocking regressions were found in the implemented registrar-batch path.

## Scope

This audit verifies the change from school-year roster based registration to registrar-batch based registration:

- Registrar CSV import creates student records and registrar batch membership records.
- Student login requires at least one active registrar batch membership.
- Election web registration is gated by the election's linked registrar batch.
- Imported batch members do not become voters until they register.
- Registered students become eligible voters.
- Non-registered batch members cannot open or cast ballots.
- Finalized voter rolls block further registration.
- Legacy school-year and verification endpoints remain present but are not part of the normal workflow.

## Automated Regression Checks

All commands were run from the repository root.

| Check | Result | Evidence |
| --- | --- | --- |
| `.\.venv\Scripts\python.exe manage.py check` | PASS | `System check identified no issues` |
| `.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` | PASS | `No changes detected` |
| `.\.venv\Scripts\python.exe manage.py test apps.accounts apps.elections apps.voting apps.audit --settings=config.settings.test` | PASS | `Ran 24 tests`, `OK` |
| Frontend template script parser through Node | PASS | `admin_panel.html`, `dashboard.html`, `ballot.html`, `results.html`, `login.html`, and `admin_login.html` each parsed successfully |
| `git diff --check` | PASS | No whitespace errors; only expected CRLF working-copy warnings |

## Live App Health Smoke

Docker status:

| Service | Result |
| --- | --- |
| `cems-db-1` | healthy |
| `cems-web-1` | healthy |

HTTP probes:

| URL | Expected | Result |
| --- | --- | --- |
| `/api/health/` | Health JSON available | `200` |
| `/` | Student login renders | `200` |
| `/dashboard/` | Redirect when unauthenticated | `302 -> /` |
| `/ballot/` | Redirect when unauthenticated | `302 -> /` |
| `/results/` | Redirect when unauthenticated | `302 -> /` |
| `/election-admin/login/` | Admin login renders | `200` |
| `/admin-panel/` | Redirect when admin is unauthenticated | `302 -> /election-admin/login/` |
| `/api/registration/available/` | Student auth required | `401` |
| `/api/admin/elections/setup/list/` | Admin auth required | `401` |

## End-to-End Registrar-Batch Smoke

A temporary smoke scenario was executed inside the Docker web container using prefix `SMOKE-RB-20260709`. The script cleaned up all temporary elections, batches, students, ballots, and admin users afterward.

Cleanup result:

```text
{'elections': 0, 'batches': 0, 'students': 0, 'admins': 0}
```

Passed assertions:

- Admin login succeeds for an Electoral Board Head.
- Admin can create a linked registrar batch.
- Linked registrar CSV import creates 2 batch membership records.
- Admin can create a separate active registrar batch.
- Separate registrar CSV import creates 1 membership record.
- Admin can create a draft campus election.
- Temporary candidates can be added for all generated positions.
- Admin can link the registrar batch and enable registration.
- Initial registration summary reports 0 approved registrations and 0 eligible voters.
- A student with no active registrar batch membership cannot log in.
- A linked-batch student can log in.
- The linked-batch student sees the election under available registrations.
- The linked-batch student can register; response status is `201 Created`.
- Registration summary reports 1 approved registration and 1 eligible voter.
- A student in another active batch can log in, but cannot see the linked election.
- A student in another active batch cannot register directly for the linked election.
- A second linked-batch student can log in before finalization.
- Admin can finalize the voter roll.
- Finalized voter roll blocks the second linked-batch student from registering.
- Admin can start the finalized election after candidates and voter roll are ready.
- The registered eligible voter can open the ballot.
- Every visible ballot position has an active candidate.
- The registered eligible voter can cast a ballot.
- The unregistered batch member cannot open the ballot.
- The unregistered batch member cannot cast a ballot.

## Verification Notes

- The registration summary API currently exposes the approved registration count as `approved`. The admin UI already reads `registrationSummary.approved`, so this is working as implemented.
- First-time web registration returns `201 Created`; repeat registration uses the existing registration and may return `200`.
- Ballot casting requires both `active` election status and the current time to be inside the election voting window.
- The smoke used Django's request stack inside the Docker app for authenticated endpoint flow, plus separate HTTP probes against `localhost:8000` for live routing and authentication behavior.

## Residual Risks And Follow-Up

- `docs/LOCAL_TESTING.md` still describes the old school-year roster workflow in its manual college-election and election-day checklist sections. That guide should be updated to describe registrar batch import, batch linking, web registration, and voter-roll finalization.
- Legacy school-year and verification endpoints still exist for compatibility. They are hidden from the normal UI workflow, but a direct API caller can still reach them with admin credentials.
- External API consumers expecting a field named `approved_registrations` would need either documentation or a compatibility alias; the current first-party UI uses `approved`.
