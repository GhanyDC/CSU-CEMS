# CEMS Codebase Reference for ChatGPT

This file is a code-centered companion to `PROJECT_BRIEFING_FOR_CHATGPT.md`.

Use it when a ChatGPT session asks for:

- current Django models
- current `VotingService` code
- project folder structure
- current routes
- current authentication flow
- settings layout

## 1. Project folder structure

Trimmed repo tree, excluding `.venv`, caches, and generated noise:

```text
CEMS/
├── apps/
│   ├── accounts/
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py
│   │   │   └── __init__.py
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   ├── urls.py
│   │   └── views.py
│   ├── audit/
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py
│   │   │   └── __init__.py
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   └── services.py
│   ├── elections/
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py
│   │   │   └── __init__.py
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   └── urls.py
│   ├── voting/
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py
│   │   │   └── __init__.py
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   ├── services.py
│   │   └── urls.py
│   └── __init__.py
├── config/
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── local.py
│   │   ├── production.py
│   │   └── test.py
│   ├── __init__.py
│   ├── asgi.py
│   ├── urls.py
│   └── wsgi.py
├── docker/
│   └── nginx.conf
├── requirements/
│   ├── base.txt
│   ├── local.txt
│   └── production.txt
├── tests/
│   ├── __init__.py
│   ├── test_authentication.py
│   ├── test_audit.py
│   ├── test_models.py
│   ├── test_rate_limiting.py
│   └── test_voting.py
├── .env.example
├── conftest.py
├── docker-compose.yml
├── Dockerfile
├── manage.py
├── PROJECT_BRIEFING_FOR_CHATGPT.md
├── CHATGPT_CODEBASE_REFERENCE.md
├── pyproject.toml
├── pytest.ini
├── README.md
├── setup.cfg
└── SETUP_GUIDE.md
```

## 2. What each top-level area does

- `apps/accounts/`: student identity and login endpoint
- `apps/elections/`: candidate model only; no real election API yet
- `apps/voting/`: vote model and transactional vote-casting service
- `apps/audit/`: audit log model and audit/logging helper
- `config/settings/`: environment-specific Django settings
- `tests/`: pytest coverage of current backend behavior
- `requirements/`: dependency split for base/local/production
- `docker-compose.yml`: local development with PostgreSQL and Django
- `Dockerfile`: container image build

## 3. Current Django models

### `apps/accounts/models.py`

Current `Student` model:

```python
"""
Accounts models — Student entity.

The Student model is the core identity model for voters.
It is intentionally NOT a Django User model because authentication
happens via student_id + date_of_birth, not username/password.
"""
import uuid
from datetime import datetime
from typing import Optional

from django.db import models
from django.utils import timezone


class Student(models.Model):
    """
    Represents an enrolled student eligible to vote.

    Authentication is via student_id + date_of_birth.
    Account locks after CEMS_MAX_FAILED_ATTEMPTS failed login attempts.
    """

    id: models.UUIDField = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    student_id: models.CharField = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Unique student identifier (e.g. matric number).",
    )
    full_name: models.CharField = models.CharField(max_length=255)
    date_of_birth: models.DateField = models.DateField()
    course: models.CharField = models.CharField(max_length=255)
    year: models.PositiveSmallIntegerField = models.PositiveSmallIntegerField()
    has_voted: models.BooleanField = models.BooleanField(
        default=False,
        db_index=True,
    )
    failed_attempts: models.PositiveIntegerField = models.PositiveIntegerField(
        default=0,
    )
    lock_until: models.DateTimeField = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Account locked until this time after exceeding failed attempts.",
    )
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["student_id"]
        verbose_name = "Student"
        verbose_name_plural = "Students"

    def __str__(self) -> str:
        return f"{self.student_id} – {self.full_name}"

    @property
    def is_locked(self) -> bool:
        """Return True if the account is currently locked."""
        if self.lock_until is None:
            return False
        return timezone.now() < self.lock_until

    def increment_failed_attempts(self, max_attempts: int, lockout_minutes: int) -> None:
        """Increment failed attempts and lock if threshold reached."""
        self.failed_attempts += 1
        if self.failed_attempts >= max_attempts:
            self.lock_until = timezone.now() + timezone.timedelta(
                minutes=lockout_minutes
            )
        self.save(update_fields=["failed_attempts", "lock_until"])

    def reset_failed_attempts(self) -> None:
        """Reset failed attempts after successful authentication."""
        self.failed_attempts = 0
        self.lock_until = None
        self.save(update_fields=["failed_attempts", "lock_until"])
```

Interpretation:

- Student identity is custom, not tied to Django's `User`
- `has_voted` is a single global boolean
- login lockout state is stored directly on the student row

### `apps/elections/models.py`

Current `Candidate` model:

```python
"""
Elections models — Candidate entity.
"""
import uuid

from django.db import models


class Candidate(models.Model):
    """
    Represents a candidate standing for a specific position.
    """

    id: models.UUIDField = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    full_name: models.CharField = models.CharField(max_length=255)
    position: models.CharField = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Position the candidate is contesting (e.g. President).",
    )
    party: models.CharField = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )
    is_active: models.BooleanField = models.BooleanField(
        default=True,
        db_index=True,
    )
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "full_name"]
        verbose_name = "Candidate"
        verbose_name_plural = "Candidates"

    def __str__(self) -> str:
        return f"{self.full_name} ({self.position})"
```

Interpretation:

- candidates are attached only to a free-text `position`
- there is no `Election` model yet
- there is no normalized `Position` table yet

### `apps/voting/models.py`

Current `Vote` model:

```python
"""
Voting models — Vote entity.

Votes store a hashed student_id (never the raw value) to preserve
ballot secrecy while still allowing one-person-one-vote enforcement.
"""
import hashlib
import uuid

from django.conf import settings
from django.db import models


class Vote(models.Model):
    """
    Immutable record of a single vote.

    The raw student_id is NEVER stored.  Instead we store a
    salted SHA-256 hash so that we can enforce one-person-one-vote
    without leaking which student voted for whom.
    """

    id: models.UUIDField = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    hashed_student_id: models.CharField = models.CharField(
        max_length=64,
        db_index=True,
        help_text="SHA-256 hash of (student_id + secret salt).",
    )
    candidate: models.ForeignKey = models.ForeignKey(
        "elections.Candidate",
        on_delete=models.PROTECT,
        related_name="votes",
    )
    position: models.CharField = models.CharField(
        max_length=100,
        help_text="Position this vote is for.",
    )
    timestamp: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Vote"
        verbose_name_plural = "Votes"

    def __str__(self) -> str:
        return f"Vote {self.id} – {self.position}"

    @staticmethod
    def hash_student_id(student_id: str) -> str:
        """
        Return a salted SHA-256 hex digest of the student_id.

        Uses DJANGO SECRET_KEY as salt so the hash cannot be
        reversed without knowledge of the secret.
        """
        salt: str = settings.SECRET_KEY
        value: str = f"{salt}:{student_id}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
```

Interpretation:

- vote rows do not store raw student IDs
- votes point to candidates and duplicate the `position` string
- there is no DB uniqueness constraint on `hashed_student_id`

### `apps/audit/models.py`

Current `AuditLog` model summary:

- event types: `login_attempt`, `vote_cast`, `suspicious_activity`
- fields:
  - `student_id_attempted`
  - `ip_address`
  - `user_agent`
  - `success`
  - `event_type`
  - `details`
  - `timestamp`
- intended as immutable-by-convention

Interpretation:

- audit logging exists and is important to the project design
- immutability is enforced in admin, not strongly at DB level

## 4. Current `VotingService` code

Current `apps/voting/services.py`:

```python
"""
Voting service — transactional vote creation with integrity checks.
"""
import logging
from typing import Optional

from django.db import transaction

from apps.accounts.models import Student
from apps.elections.models import Candidate
from apps.voting.models import Vote

logger = logging.getLogger("cems.application")


class VoteAlreadyCastError(Exception):
    """Raised when a student attempts to vote more than once."""

    pass


class VotingService:
    """
    Encapsulates voting business logic with transactional integrity.
    """

    @staticmethod
    @transaction.atomic
    def cast_vote(student: Student, candidate: Candidate) -> Vote:
        """
        Atomically record a vote.

        1. Lock the student row (SELECT … FOR UPDATE) to prevent races.
        2. Verify the student has not already voted.
        3. Create the Vote with a hashed student_id.
        4. Mark the student as having voted.

        Raises VoteAlreadyCastError if the student already voted.
        """
        # Lock row to prevent concurrent double-vote
        locked_student: Student = (
            Student.objects.select_for_update().get(pk=student.pk)
        )

        if locked_student.has_voted:
            logger.warning(
                "Double vote attempt blocked for student_id=%s",
                locked_student.student_id,
            )
            raise VoteAlreadyCastError("This student has already voted.")

        hashed_id: str = Vote.hash_student_id(locked_student.student_id)

        # Additional check: ensure no vote with this hash exists
        if Vote.objects.filter(hashed_student_id=hashed_id).exists():
            logger.warning(
                "Hashed student_id collision detected for student_id=%s",
                locked_student.student_id,
            )
            raise VoteAlreadyCastError("Vote record already exists for this student.")

        vote: Vote = Vote.objects.create(
            hashed_student_id=hashed_id,
            candidate=candidate,
            position=candidate.position,
        )

        locked_student.has_voted = True
        locked_student.save(update_fields=["has_voted"])

        logger.info(
            "Vote cast successfully: vote_id=%s, position=%s",
            vote.id,
            vote.position,
        )
        return vote
```

Important interpretation:

- this is the core one-person-one-vote enforcement logic
- it is designed for one total vote, not one vote per position
- it relies on:
  - `Student.has_voted`
  - `select_for_update()`
  - existence check on `Vote.hashed_student_id`
- it currently does not log a `vote_cast` audit record itself
- it currently has no HTTP endpoint around it

## 5. Current URL structure

### Root URLs

Current `config/urls.py`:

```python
"""
CEMS URL Configuration.
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns: list = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls", namespace="accounts")),
    path("api/elections/", include("apps.elections.urls", namespace="elections")),
    path("api/voting/", include("apps.voting.urls", namespace="voting")),
]

if settings.DEBUG and "debug_toolbar" in settings.INSTALLED_APPS:
    import debug_toolbar
    urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
```

### Accounts URLs

Current `apps/accounts/urls.py`:

```python
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns: list = [
    path("login/", views.student_login, name="login"),
]
```

### Elections URLs

Current `apps/elections/urls.py`:

```python
from django.urls import path

app_name = "elections"

urlpatterns: list = [
    # Election endpoints will be added in future phases
]
```

### Voting URLs

Current `apps/voting/urls.py`:

```python
from django.urls import path

app_name = "voting"

urlpatterns: list = [
    # Voting endpoints will be added in future phases
]
```

Interpretation:

- only one API route is implemented today: `POST /api/auth/login/`
- voting and election namespaces are placeholders

## 6. Current authentication flow

Current auth endpoint:

- `POST /api/auth/login/`

Current `student_login` behavior summary:

- accepts JSON or form data
- required fields:
  - `student_id`
  - `date_of_birth`
- uses:
  - CSRF protection
  - IP rate limit of `10/m`
  - generic error messages
  - audit logging
- on success, stores in session:
  - `authenticated_student_id`
  - `student_id`
- response payload:
  - `success`
  - `student_id`
  - `full_name`
  - `has_voted`

Security-relevant details:

- unknown student and wrong DOB both return generic `401`
- locked accounts return a separate lock message
- failed attempts increment on wrong DOB

## 7. Settings layout and behavior

### `manage.py`

Current default settings module:

```python
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
```

Interpretation:

- local development defaults to `config.settings.local`

### `config/settings/base.py`

Important points:

- PostgreSQL is the default DB engine
- timezone is `UTC`
- CSRF/session cookies are secure by default
- HSTS and SSL redirect are enabled by default
- installed local apps:
  - `apps.accounts`
  - `apps.elections`
  - `apps.voting`
  - `apps.audit`
- application constants:
  - `CEMS_MAX_FAILED_ATTEMPTS`
  - `CEMS_LOCKOUT_MINUTES`
- log files:
  - `logs/security.log`
  - `logs/login_attempts.log`
  - `logs/application.log`

### `config/settings/local.py`

Important points:

- `DEBUG = True`
- relaxed cookie/SSL settings for local development
- debug toolbar enabled

### `config/settings/production.py`

Important points:

- `DEBUG = False`
- WhiteNoise middleware added
- static files use compressed manifest storage

### `config/settings/test.py`

Important points:

- uses in-memory SQLite
- disables debug toolbar
- disables rate limiting in tests

Important caveat:

- because tests run on SQLite, they do not fully validate PostgreSQL row-locking behavior for `select_for_update()`

## 8. Current admin behavior

### Student admin

- manageable in admin
- shows voting and lockout-related fields

### Candidate admin

- manageable in admin

### Vote admin

- read-only
- add/change/delete disabled

### AuditLog admin

- read-only
- add/change/delete disabled

Interpretation:

- the code treats votes and audit logs as immutable operational records

## 9. Current tests

Current pytest files:

- `tests/test_authentication.py`
- `tests/test_audit.py`
- `tests/test_models.py`
- `tests/test_rate_limiting.py`
- `tests/test_voting.py`

What they cover:

- authentication behavior
- audit logging behavior
- basic model integrity
- rate limiting behavior
- vote creation and double-vote prevention

Observed during analysis:

- `pytest -q` passed with `39 passed`
- coverage was reported as `95%`

## 10. Current implementation boundaries

What is definitely implemented:

- student login
- failed-login lockouts
- audit logging
- candidate storage
- vote storage
- transactional vote-casting service
- admin inspection of votes and audit logs

What is definitely not implemented yet:

- election-cycle model
- real ballot API
- vote submission endpoint
- candidate listing endpoint
- results publication flow
- logout endpoint
- authenticated voter session helpers beyond direct session writes

## 11. Current design limitations that ChatGPT should keep in mind

- `Student.has_voted` is global, so the schema is not ready for multi-position campus ballots
- `Candidate.position` is free text, not normalized
- `Vote.hashed_student_id` has no DB-level unique constraint
- audit immutability is mostly application/admin-level, not DB-enforced
- `VotingService` is not yet connected to an HTTP endpoint
- concurrency safety is intended, but real proof still needs PostgreSQL concurrency tests

## 12. Paste-ready short context block

If ChatGPT asks only for the essentials, paste this:

```text
Project: CEMS (Campus Election Management System)
Stack: Django backend, PostgreSQL in real envs, SQLite in tests, Docker for local dev

Current implemented models:
- Student: student_id, full_name, date_of_birth, course, year, has_voted, failed_attempts, lock_until
- Candidate: full_name, position, party, is_active
- Vote: hashed_student_id, candidate, position, timestamp
- AuditLog: student_id_attempted, ip_address, user_agent, success, event_type, details, timestamp

Current implemented API:
- POST /api/auth/login/

Current voting logic:
- VotingService.cast_vote(student, candidate) uses transaction.atomic + select_for_update on Student
- blocks double voting using Student.has_voted and an existing Vote hash check
- creates Vote(hashed_student_id, candidate, position)
- marks Student.has_voted = True

Current missing pieces:
- no vote API endpoint
- no election-cycle model
- no candidate listing API
- no results API
- no real multi-position ballot model
```
