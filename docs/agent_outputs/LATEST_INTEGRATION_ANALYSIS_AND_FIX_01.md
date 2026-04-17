# Latest Integration Analysis and Fix 01

## Latest commit

- Commit: `3a8e8444c83df1454697145c75c905ddeef24ae7`
- Message: `cleaning and enhancement`

## What the latest integration changed

The latest commit introduced a broad hybrid-election integration across backend, frontend, tests, and Docker/runtime setup:

- added `Election.voting_mode` with `online` and `hybrid`
- added hybrid import models and migration for onsite roster and tally batches
- added `HybridElectionService` and hybrid admin endpoints
- extended admin setup/detail payloads and admin UI with hybrid canvass controls
- changed result and turnout computation to support online, onsite, and combined figures
- added a Docker entrypoint and adjusted local runtime wiring

## Regression risks found

Two categories of regression showed up after reviewing the diff and then running the project locally.

### 1. Hybrid publish/readiness drift

The hybrid bundle introduced a publish-readiness bug:

1. publish readiness only checked for the presence of an active roster batch and an active tally batch
2. re-importing the onsite roster did not invalidate the previously active onsite tally
3. onsite tally import accepted impossible per-position totals relative to the imported onsite turnout

That combination could leave a hybrid election looking publish-ready even when the active roster and active tally no longer matched, or when the tally exceeded what the onsite participant count could legally support.

### 2. Local Docker workflow drift

The runtime integration also introduced local inconsistencies:

1. `docker/entrypoint.sh` always launched Gunicorn directly and ignored the Compose `command`, so `migrate` and `collectstatic` were skipped on startup
2. `docker-compose.yml` hard-coded host port `5432:5432`, which collided immediately on this machine with another local PostgreSQL container
3. local `DEBUG` static serving only exposed the repo `static/` directory, so installed-app static assets such as Django Debug Toolbar returned `404`
4. the existing local test guide still pointed to `http://localhost:8000/election-admin/`, but the real admin login route is `http://localhost:8000/election-admin/login/`

## Root cause

### Hybrid logic root cause

The integration coupled hybrid publish readiness to batch existence instead of batch validity.

- `HybridElectionService.has_required_imports()` returned `True` as soon as both active batch types existed
- `import_onsite_roster()` superseded the prior roster batch but left the prior tally batch active
- `import_onsite_tally()` validated row identity and completeness, but not per-position vote ceilings against the active onsite roster size

### Local runtime root cause

The local runtime changes introduced a few separate mismatches.

- Compose was configured to run `migrate`, then `collectstatic`, then Gunicorn
- the entrypoint ignored all passed arguments and always executed Gunicorn itself
- the host database port was made absolute instead of configurable for local machines that already use `5432`
- `config/urls.py` used `static(..., document_root=settings.STATICFILES_DIRS[0])`, which bypassed Django staticfiles finders and missed installed-app assets

## Files changed in the fix

- `apps/elections/hybrid_services.py`
- `apps/elections/tests.py`
- `config/urls.py`
- `docker/entrypoint.sh`
- `docker-compose.yml`
- `.env.example`
- `.gitignore`

## What was fixed

### 1. Hybrid publish readiness now validates state, not just batch presence

A hybrid election is now publish-ready only when:

- an active onsite roster exists
- an active onsite tally exists
- the active tally does not predate the current active roster
- the active tally stays within the maximum vote capacity implied by onsite turnout and `max_selections`

### 2. Re-importing the onsite roster now clears stale active tallies

When a new onsite roster import succeeds, any active onsite tally batch is now superseded automatically. This forces the tally to be re-imported for the current roster and prevents stale publish-ready states.

### 3. Onsite tally imports now reject impossible totals

Per-position onsite tally totals are now validated against:

- `onsite participant count * position.max_selections`

This blocks invalid imports such as a single-seat position receiving more onsite votes than there are onsite participants.

### 4. Docker startup now honors the Compose command

`docker/entrypoint.sh` now prepares writable directories and then:

- runs the passed container command as the `cems` user when a command is provided
- falls back to direct Gunicorn launch only when no command is provided

That preserves the intended Compose startup path, including `migrate` and `collectstatic`.

### 5. Local PostgreSQL host port is now configurable

The database service now maps:

- `${POSTGRES_HOST_PORT:-5433}:5432`

This keeps Compose usable on machines where `5432` is already occupied and matches the updated `.env.example`.

### 6. Local-only runtime artifacts are ignored

Added ignores for:

- `.gunicorn/`
- `.pytest_cache/`

This keeps local verification runs from polluting `git status`.

### 7. Local debug static serving now uses Django staticfiles finders

`config/urls.py` now uses `staticfiles_urlpatterns()` in `DEBUG` mode instead of serving only `STATICFILES_DIRS[0]`.

That fixed browser-side `404` responses for installed-app static assets, including:

- `/static/debug_toolbar/css/print.css`

## Tests added/updated

Updated `apps/elections/tests.py` with focused regression coverage:

- `test_roster_reimport_supersedes_active_tally_and_blocks_publish`
- `test_tally_import_rejects_position_totals_above_onsite_turnout_capacity`

Existing hybrid tests still pass, including publish-gate and student result-visibility coverage.

## Validation run

Executed successfully:

- `python manage.py test apps.elections --settings=config.settings.test`
- `python manage.py test --settings=config.settings.test`
- `python manage.py makemigrations --check --dry-run --settings=config.settings.test`
- `docker compose config`
- `docker compose up --build -d`
- `docker compose exec web python manage.py seed_colleges`
- `docker compose exec web python manage.py generate_pilot_data --clear --students 200`
- `docker compose exec web python manage.py test apps.elections --settings=config.settings.test`
- `docker compose exec web python manage.py check`
- host smoke checks:
  - `http://localhost:8000/api/health/` returned `{"status":"ok"}`
  - `http://localhost:8000/` returned `200`
  - `http://localhost:8000/election-admin/login/` returned `200`
  - `http://localhost:8000/static/debug_toolbar/css/print.css` returned `200`
- live auth smoke checks inside the running container:
  - seeded student login succeeded
  - seeded admin login (`eb_head`) succeeded
  - admin election list endpoint returned the pilot election in `draft`

## Intentionally not changed

The fix did not change the following intended behaviors:

- admin roles remain `EB Head`, `Operator`, `Tally Watcher`
- no permanent monitoring tab was added
- no permanent readiness tab was added
- student results remain unavailable before `Published`
- role-based tally visibility rules remain unchanged
- voter-roll protections remain unchanged
- no schema or migration changes were added for this fix
