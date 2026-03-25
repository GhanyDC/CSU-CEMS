# CEMS Project Briefing for ChatGPT

Use this document as the authoritative context handoff for any ChatGPT session that will help design, review, extend, or harden this project.

## 1. Project identity

- Project name: Campus Election Management System (`CEMS`)
- Tech stack: Django backend, PostgreSQL in real environments, SQLite in tests, Docker-based local dev
- Repository type: backend-focused service, not a complete full-stack election product
- Primary design goal: secure student authentication, auditable security events, and double-voting prevention
- Current maturity: solid backend foundation for a prototype or internal pilot, but not yet complete enough for a real campus-wide election without additional work

## 2. High-confidence summary of what exists today

This repository currently implements:

- A `Student` model used as the voter identity source
- A `Candidate` model for election candidates
- A `Vote` model that stores a salted hash of `student_id` instead of the raw student ID
- An `AuditLog` model for login/vote/security event records
- A working login API at `/api/auth/login/`
- A transactional voting service in Python code, but no HTTP voting endpoint yet
- Django admin pages for managing students/candidates and read-only inspection of votes/audit logs
- A strong automated unit/integration test suite for the existing scope

This repository does not currently implement:

- A ballot API
- A vote submission API endpoint
- A candidate listing API
- An election configuration model with start/end times
- A results/tally API
- A logout endpoint
- A complete frontend
- Real role separation for election officers vs voters
- End-to-end concurrency testing against PostgreSQL

## 3. Current directory map

- `config/`: Django project settings, root URLs, WSGI/ASGI
- `apps/accounts/`: student identity model and login endpoint
- `apps/elections/`: candidate model only
- `apps/voting/`: vote model and vote-casting service
- `apps/audit/`: immutable-by-convention audit log and logging helper
- `tests/`: pytest suite for auth, voting logic, models, rate limiting, audit logging
- `docker-compose.yml`, `Dockerfile`: local/dev and runtime container setup
- `README.md`, `SETUP_GUIDE.md`: setup and project overview docs

## 4. Core data model

### `Student`

Purpose:

- Represents an eligible voter
- Acts as the authentication subject
- Tracks whether the student has already voted
- Tracks failed login attempts and lockout state

Important fields:

- `id`: UUID primary key
- `student_id`: unique campus identifier
- `full_name`
- `date_of_birth`
- `course`
- `year`
- `has_voted`: boolean
- `failed_attempts`
- `lock_until`
- `created_at`, `updated_at`

Behavior:

- Authentication uses `student_id + date_of_birth`
- `is_locked` checks whether `lock_until` is still in the future
- `increment_failed_attempts()` increments failures and locks the account after threshold
- `reset_failed_attempts()` clears lock/failure state after successful login

Important architectural implication:

- `has_voted` is global, not per position and not per election cycle
- That means the current model supports only one total vote per student across the whole system unless the schema is redesigned

### `Candidate`

Purpose:

- Represents a candidate contesting a position

Important fields:

- `id`: UUID primary key
- `full_name`
- `position`: free-text string, not a normalized relation
- `party`
- `is_active`
- `created_at`, `updated_at`

Important architectural implication:

- There is no `Election`, `Ballot`, or `Position` table
- `position` is plain text, so validation and reporting are weaker than they should be for a production election system
- There is no election cycle separation, so multiple semesters/years would conflict conceptually

### `Vote`

Purpose:

- Stores one recorded vote while avoiding storage of the raw student ID

Important fields:

- `id`: UUID primary key
- `hashed_student_id`: SHA-256 of `SECRET_KEY:student_id`
- `candidate`: foreign key to `Candidate`
- `position`: copied from `candidate.position`
- `timestamp`

Behavior:

- `hash_student_id(student_id)` uses Django `SECRET_KEY` as salt
- Vote rows are treated as immutable by application design

Important architectural implication:

- There is no database-level unique constraint on `hashed_student_id`
- One-person-one-vote is enforced mainly in service logic plus `Student.has_voted`
- Manual DB writes or future code paths could bypass that protection if not carefully controlled

### `AuditLog`

Purpose:

- Records security-relevant actions

Event types:

- `login_attempt`
- `vote_cast`
- `suspicious_activity`

Important fields:

- `student_id_attempted`
- `ip_address`
- `user_agent`
- `success`
- `event_type`
- `details`
- `timestamp`

Important architectural implication:

- Audit records are treated as immutable by admin restrictions and convention
- There is no hard database-level immutability enforcement

## 5. Current request flow

### Authentication flow

Implemented endpoint:

- `POST /api/auth/login/`

Accepted input:

- `student_id`
- `date_of_birth` in `YYYY-MM-DD`

Flow:

1. Request is CSRF-protected and rate-limited by IP
2. Body is parsed as JSON or form data
3. Missing/invalid fields return `400`
4. Student lookup is performed by `student_id`
5. Unknown student returns generic `401`
6. Locked account returns `401`
7. Wrong DOB increments failed attempts, may lock account, returns generic `401`
8. Correct DOB resets failed attempts
9. Audit log is written
10. Session stores:
   - `authenticated_student_id`
   - `student_id`
11. Response returns:
   - `success`
   - `student_id`
   - `full_name`
   - `has_voted`

Security notes:

- The API intentionally avoids revealing whether a student ID exists
- Rate limiting is IP-based, not account-based
- Session auth is used after login

Missing related auth functionality:

- No logout endpoint
- No "who am I" endpoint
- No session/auth middleware for a voter-only API surface
- No CSRF token bootstrap endpoint for SPA or mobile-style clients

### Voting flow

Current state:

- Implemented as Python service logic only
- No HTTP endpoint currently exposes voting to clients

Service:

- `VotingService.cast_vote(student, candidate)`

Flow:

1. Open atomic DB transaction
2. Lock the student row with `select_for_update()`
3. Check `student.has_voted`
4. Hash `student_id`
5. Check whether any vote already exists for that hash
6. Create vote row
7. Mark student `has_voted = True`
8. Return created vote

Strengths:

- Sensible transactional flow
- Explicit race-prevention intent
- Protects raw student IDs from being stored in vote rows

Current limitations:

- No audit logging is performed inside `VotingService.cast_vote()`
- No API endpoint calls the service yet
- No permission/auth wrapper around vote casting exists yet
- No support for multi-position ballots
- No support for abstain/blank voting
- No election window validation

## 6. URL surface today

Defined root routes:

- `/admin/`
- `/api/auth/`
- `/api/elections/`
- `/api/voting/`

Actually implemented API route:

- `/api/auth/login/`

Namespaces that exist but are effectively placeholders:

- `apps.elections.urls`
- `apps.voting.urls`

These URL modules are present but contain no real endpoints yet.

## 7. Security posture

### Strong points already present

- Generic login failure messaging prevents student enumeration
- Failed-login counting and timed account lockout
- IP-based rate limiting on login
- CSRF protection enabled on login
- Secure cookie defaults in base settings
- HSTS and SSL redirect defaults in production settings
- Audit log table plus structured log files
- Vote creation designed around atomic DB transaction
- UUID primary keys across domain entities
- Votes do not store raw student IDs
- Votes and audit logs are read-only in Django admin

### Important caveats

- Authentication is based on `student_id + DOB`, which may be too weak for a high-stakes election if those values are easy to know or guess
- Tests do not prove PostgreSQL row-lock behavior because test settings use SQLite
- Audit immutability is not enforced at DB level
- Vote uniqueness is not enforced at DB level
- Rate limiting is only on login, not on future voting/result/admin APIs
- No signed receipts, verifiable tally mechanism, or independent audit export exists

## 8. Testing status

Command run during analysis:

```bash
pytest -q
```

Observed result:

- `39 passed`
- coverage reported as `95%`
- one warning related to `.pytest_cache` write permissions

What tests cover well:

- Login success/failure behavior
- Generic auth errors
- Failed-attempt increments and lockouts
- Audit record creation
- Vote hashing behavior
- Double-vote prevention through service logic
- Basic model constraints

What tests do not yet prove:

- Real PostgreSQL concurrency safety under simultaneous vote attempts
- Full browser/session/CSRF behavior in a real frontend
- Any real voting API contract
- Any election setup, candidate listing, results, or admin workflow beyond Django admin basics
- Disaster recovery or data integrity after crashes

## 9. Environment and deployment notes

### Settings layout

- `config.settings.base`
- `config.settings.local`
- `config.settings.production`
- `config.settings.test`

Important behavior:

- Base settings assume PostgreSQL
- Test settings switch to in-memory SQLite
- Local settings enable debug toolbar and relax transport security
- Production settings add WhiteNoise and keep hardened defaults

### Notable inconsistency

Repository documentation says the stack targets Django `5.1`, but the test run in this environment reported Django `6.0.2`.

Interpretation:

- The repo requirements declare `Django>=5.1,<5.2`
- The currently active environment used for the test run appears to have Django 6 installed
- ChatGPT should not assume the runtime matches the documented version without re-checking the actual environment

### Container note

The `Dockerfile` installs from `requirements/local.txt`, not `requirements/production.txt`.

Why this matters:

- The runtime image currently includes local/dev/test dependencies
- Production images should usually install from `requirements/production.txt` or a locked prod dependency set instead

## 10. Concrete risks before using this in a real election

These are the highest-value issues to treat as blockers or near-blockers.

### Blocker: the product is not feature-complete for a real election

Reason:

- There is no public voting endpoint
- There is no candidate listing endpoint
- There is no election-cycle model
- There is no results computation or publication workflow

### Blocker: the current schema does not model a real ballot

Reason:

- `Student.has_voted` is global
- `Vote.hashed_student_id` is checked globally
- `Candidate.position` is plain text

Effect:

- The current design behaves like one total vote ever, not one vote per position in a campus election with multiple offices

### High risk: concurrency safety is designed, not fully proven

Reason:

- `select_for_update()` is meaningful in PostgreSQL
- test suite uses SQLite, which does not validate the same locking semantics

Effect:

- The most critical election guarantee should still be tested against real PostgreSQL with concurrent requests

### High risk: audit and vote protections rely partly on convention

Reason:

- Read-only Django admin is good, but DB-level constraints are still limited

Effect:

- A future code path, migration, script, or manual operation could alter data unless stronger protections are added

### High risk: authentication may be too weak for election stakes

Reason:

- `student_id` and date of birth are often knowable within a campus environment

Effect:

- Credential guessing, coercion, or impersonation risk may be unacceptable without a second factor, one-time token, or controlled credential issuance

## 11. Recommended redesign direction for election readiness

If ChatGPT is asked to improve this system for real election use, it should push toward these structural changes.

### Data model upgrades

Add explicit domain models such as:

- `Election`
- `Position`
- `Ballot`
- `BallotSelection` or `VoteSelection`
- `VoterSession` or `AuthenticatedSession`

Recommended direction:

- `Election`: name, status, start/end, publication state
- `Position`: belongs to election, has max selections allowed
- `Candidate`: belongs to a specific position
- `Ballot`: one ballot submission per voter per election
- `BallotSelection`: one selected candidate per ballot per position

This would let the system support:

- multiple positions in one election
- multiple election cycles over time
- better validation and results tallying

### Database hardening

Recommended direction:

- Add DB uniqueness where business rules require it
- Add explicit indexes for tally/report queries
- Consider append-only patterns for audit data
- Add DB constraints to prevent logically impossible states

### API surface

Recommended direction:

- `POST /api/auth/login/`
- `POST /api/auth/logout/`
- `GET /api/auth/me/`
- `GET /api/elections/current/`
- `GET /api/elections/current/ballot/`
- `POST /api/voting/cast/`
- `GET /api/voting/status/`
- `GET /api/results/` with strict publication control

### Operational hardening

Recommended direction:

- PostgreSQL-only concurrency tests
- load testing before election day
- backup/restore rehearsal
- admin runbook for incident response
- clock/timezone verification
- immutable exports of audit logs and final tallies
- deployment freeze before election period

## 12. Specific things ChatGPT should not assume

- Do not assume there is already a working frontend
- Do not assume students can currently cast votes through HTTP
- Do not assume multi-position voting is implemented
- Do not assume results logic exists
- Do not assume SQLite tests prove production race safety
- Do not assume the active Django version is the same as the documented one
- Do not assume audit immutability is fully enforced at the database layer

## 13. Best-practice instructions for future ChatGPT sessions

When helping with this project, ChatGPT should:

- treat correctness and election integrity as higher priority than speed
- prefer conservative, explicit designs over clever shortcuts
- identify mismatch between current code and real election requirements
- ask whether the intended rule is:
  - one vote total
  - one vote per position
  - one ballot containing many selections
- keep PostgreSQL behavior in mind whenever concurrency is discussed
- prefer database-backed guarantees over application-only guarantees when feasible
- preserve secrecy of ballots while maintaining auditability of security events
- avoid suggestions that leak how a specific student voted
- highlight any change that could affect fairness, anonymity, or double-voting prevention

## 14. Paste-ready prompt for a browser ChatGPT session

Use the following as the starting message in another ChatGPT session:

```text
I am working on a Django-based Campus Election Management System called CEMS. Treat this as a high-stakes election software review and design task where correctness, integrity, auditability, and prevention of double voting matter more than speed or convenience.

Current reality of the codebase:

- It is a backend-first Django project.
- The implemented working API is only POST /api/auth/login/.
- Authentication is by student_id + date_of_birth.
- Students are stored in a Student model with fields including student_id, full_name, date_of_birth, course, year, has_voted, failed_attempts, and lock_until.
- Candidates are stored in a Candidate model with full_name, position, party, and is_active.
- Votes are stored in a Vote model with hashed_student_id, candidate, position, and timestamp.
- Vote hashing uses SHA-256 over SECRET_KEY:student_id.
- There is an AuditLog model for login_attempt, vote_cast, and suspicious_activity events.
- Vote casting currently exists only as a Python service method using transaction.atomic plus select_for_update on the Student row. There is no public vote API endpoint yet.
- Elections and voting URL modules exist but have no real endpoints yet.
- The current schema does not yet model a real election cycle or multi-position ballot correctly. Student.has_voted is global, and vote uniqueness is effectively global too.
- Tests pass and cover the current scope well, but they run on SQLite, so PostgreSQL locking/concurrency behavior is not fully proven.

I want you to help as if you fully understand this codebase. Before proposing changes, first reason from the current actual state above, identify what is already implemented versus missing, then help design or review changes with a production-grade election mindset. Flag weak assumptions aggressively, especially around ballot modeling, concurrency, security, auditability, and deployment safety.
```

## 15. Bottom-line assessment

This repository is a good secure backend starting point, but it is not yet a complete election system. It should be treated as a strong foundation for further hardening and expansion, not as election-ready software in its current form.
