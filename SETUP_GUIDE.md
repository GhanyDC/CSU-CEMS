# CEMS – Complete Setup Guide

Step-by-step instructions for setting up the Campus Election Management System from scratch on a new machine.

---

## Table of Contents

1. [System Prerequisites](#1-system-prerequisites)
2. [Install Required Software](#2-install-required-software)
3. [Clone the Repository](#3-clone-the-repository)
4. [Configure Environment Variables](#4-configure-environment-variables)
5. [Docker Setup (Recommended)](#5-docker-setup-recommended)
6. [Local Python Setup (Alternative)](#6-local-python-setup-alternative)
7. [Database Initialization](#7-database-initialization)
8. [Create a Superuser](#8-create-a-superuser)
9. [Verify the Setup](#9-verify-the-setup)
10. [Running Tests](#10-running-tests)
11. [Optional: Pre-commit Hooks](#11-optional-pre-commit-hooks)
12. [Useful Commands Reference](#12-useful-commands-reference)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. System Prerequisites

Before you begin, ensure your machine has the following:

| Requirement | Minimum Version | Notes |
|---|---|---|
| **Operating System** | Windows 10/11, macOS 12+, Ubuntu 20.04+ | |
| **Python** | 3.12+ | For local setup only |
| **Docker Desktop** | 4.20+ | Required for Docker setup |
| **Git** | 2.40+ | For version control |
| **PostgreSQL** | 16+ | Only needed for local setup (Docker includes it) |

---

## 2. Install Required Software

### 2.1 Git

**Windows:**
Download from https://git-scm.com/download/win and run the installer.

**macOS:**
```bash
brew install git
```

**Ubuntu/Debian:**
```bash
sudo apt update && sudo apt install git -y
```

Verify:
```bash
git --version
```

---

### 2.2 Docker Desktop

Docker Desktop includes both Docker Engine and Docker Compose.

**Windows / macOS:**
Download and install from https://www.docker.com/products/docker-desktop/

After installation:
- Open Docker Desktop and ensure it is **running** (look for the whale icon in the system tray)
- Enable WSL2 backend on Windows when prompted

**Ubuntu/Debian:**
```bash
# Add Docker's official GPG key
sudo apt update
sudo apt install ca-certificates curl -y
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the Docker repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin -y

# Allow your user to run Docker without sudo
sudo usermod -aG docker $USER
newgrp docker
```

Verify:
```bash
docker --version
docker compose version
```

---

### 2.3 Python 3.12+ (Local setup only — skip if using Docker)

**Windows:**
Download from https://www.python.org/downloads/ and check **"Add Python to PATH"** during installation.

**macOS:**
```bash
brew install python@3.12
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3.12-dev -y
```

Verify:
```bash
python --version      # Windows
python3 --version     # macOS / Linux
```

---

## 3. Clone the Repository

```bash
git clone <your-repository-url> CEMS
cd CEMS
```

The project should look like this:
```
CEMS/
├── apps/
├── config/
├── docker/
├── requirements/
├── tests/
├── Dockerfile
├── docker-compose.yml
├── manage.py
├── .env.example
└── pytest.ini
```

---

## 4. Configure Environment Variables

The application reads all secrets and configuration from a `.env` file. **Never commit this file to version control.**

### Step 1 — Copy the example file

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

**macOS / Linux:**
```bash
cp .env.example .env
```

### Step 2 — Edit the `.env` file

Open `.env` in any text editor and fill in the values:

```env
# Django
DJANGO_SECRET_KEY=replace-this-with-a-long-random-string
DJANGO_SETTINGS_MODULE=config.settings.local
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
DEBUG=True

# PostgreSQL
POSTGRES_DB=cems
POSTGRES_USER=cems
POSTGRES_PASSWORD=choose-a-strong-password-here
POSTGRES_HOST=db
POSTGRES_PORT=5432

# CEMS application
CEMS_MAX_FAILED_ATTEMPTS=5
CEMS_LOCKOUT_MINUTES=30
```

### Step 3 — Generate a secure SECRET_KEY

Run one of the following to generate a strong key:

**Python:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

**PowerShell:**
```powershell
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Copy the output and paste it as the value of `DJANGO_SECRET_KEY` in your `.env` file.

> ⚠️ **Security:** Never use the same `SECRET_KEY` in production. Generate a separate one for each environment.

---

## 5. Docker Setup (Recommended)

This is the simplest way to get started. Docker handles PostgreSQL, Django, and all dependencies automatically.

### Step 1 — Ensure Docker Desktop is running

Open Docker Desktop and wait until the status shows **"Engine running"**.

### Step 2 — Build and start the containers

```bash
docker compose up --build
```

This command:
- Builds the Django application image
- Pulls the PostgreSQL 16 image
- Starts both services
- The Django container automatically runs `python manage.py migrate` on first boot

First run will take 2–5 minutes to download images and install packages. Subsequent starts are fast.

You should see output like:
```
db-1   | database system is ready to accept connections
web-1  | Operations to perform: Apply all migrations
web-1  | Running migrations: ...
web-1  | Starting development server at http://0.0.0.0:8000/
```

### Step 3 — Verify the app is running

Open your browser and go to: http://localhost:8000/admin/

You should see the Django administration login page.

### Starting and stopping

```bash
# Start in foreground (see logs)
docker compose up

# Start in background
docker compose up -d

# Stop
docker compose down

# Stop and remove all data (wipe database)
docker compose down -v
```

---

## 6. Local Python Setup (Alternative)

Use this if you prefer not to use Docker, or if you want to run tests directly on your machine. You still need PostgreSQL installed locally.

### Step 1 — Create a virtual environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Your terminal prompt should now show `(.venv)`.

### Step 2 — Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements/local.txt
```

This installs Django, PostgreSQL driver, testing tools, debug toolbar, and all code-quality tools.

### Step 3 — Install and start PostgreSQL locally

**Windows:**
Download from https://www.postgresql.org/download/windows/ and run the installer.
During installation, set a password for the `postgres` superuser.

**macOS:**
```bash
brew install postgresql@16
brew services start postgresql@16
```

**Ubuntu/Debian:**
```bash
sudo apt install postgresql postgresql-contrib -y
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### Step 4 — Create the database and user

Connect to PostgreSQL:

**Windows (in PostgreSQL shell or psql):**
```powershell
psql -U postgres
```

**macOS / Linux:**
```bash
sudo -u postgres psql
```

Then run these SQL commands (replace the password with the one in your `.env`):
```sql
CREATE DATABASE cems;
CREATE USER cems WITH PASSWORD 'password';
ALTER ROLE cems SET client_encoding TO 'utf8';
ALTER ROLE cems SET default_transaction_isolation TO 'read committed';
ALTER ROLE cems SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE cems TO cems;
\q
```

### Step 5 — Update `.env` for local PostgreSQL

Change `POSTGRES_HOST` in your `.env` from `db` (Docker hostname) to `localhost`:
```env
POSTGRES_HOST=localhost
```

---

## 7. Database Initialization

### Docker setup

Migrations run automatically when the container starts. To run them manually:

```bash
docker compose exec web python manage.py migrate
```

### Local setup

```bash
python manage.py migrate
```

Expected output:
```
Operations to perform:
  Apply all migrations: accounts, admin, audit, auth, contenttypes, elections, sessions, voting
Running migrations:
  Applying accounts.0001_initial... OK
  Applying audit.0001_initial... OK
  Applying elections.0001_initial... OK
  Applying voting.0001_initial... OK
  ...
```

---

## 8. Create a Superuser

A superuser lets you access the Django admin panel at `/admin/`.

### Docker:
```bash
docker compose exec web python manage.py createsuperuser
```

### Local:
```bash
python manage.py createsuperuser
```

You will be prompted:
```
Username: admin
Email address: admin@example.com
Password: (enter a strong password)
Password (again):
Superuser created successfully.
```

---

## 9. Verify the Setup

### Check the admin panel

1. Go to http://localhost:8000/admin/
2. Log in with the superuser credentials you just created
3. You should see sections for: **Students**, **Candidates**, **Votes** (read-only), **Audit Logs** (read-only)

### Test the login API endpoint

Use `curl` or any API client (Postman, Insomnia):

```bash
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"student_id": "STU001", "date_of_birth": "2000-01-01"}'
```

Expected response (no student exists yet):
```json
{"success": false, "error": "Invalid credentials. Please try again."}
```

**PowerShell equivalent:**
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/auth/login/" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"student_id": "STU001", "date_of_birth": "2000-01-01"}'
```

---

## 10. Running Tests

Tests use an in-memory SQLite database and do not require a running PostgreSQL instance.

### Docker:
```bash
docker compose exec web python -m pytest -v
```

### Local (with virtual environment activated):
```bash
# Set the test settings module
$env:DJANGO_SETTINGS_MODULE="config.settings.test"   # PowerShell
export DJANGO_SETTINGS_MODULE=config.settings.test   # macOS / Linux

python -m pytest -v
```

Expected output:
```
collected 39 items

tests/test_audit.py::TestAuditLogging::test_create_login_attempt_record PASSED
tests/test_authentication.py::TestStudentAuthentication::test_successful_login PASSED
tests/test_voting.py::TestVoteCreation::test_cannot_vote_twice PASSED
...
======================== 39 passed in 1.85s ========================
```

### Run with coverage report:
```bash
python -m pytest --cov=apps --cov-report=html
# Open htmlcov/index.html in your browser
```

### Run only a specific test file:
```bash
python -m pytest tests/test_authentication.py -v
```

---

## 11. Optional: Pre-commit Hooks

Pre-commit hooks automatically run Black, isort, and flake8 before every `git commit`.

### Install pre-commit:
```bash
pip install pre-commit
```

### Install the hooks into the repository:
```bash
pre-commit install
```

### Test all hooks manually:
```bash
pre-commit run --all-files
```

From now on, every `git commit` will automatically format and lint your code.

---

## 12. Useful Commands Reference

### Docker commands

| Action | Command |
|---|---|
| Start all services | `docker compose up` |
| Start in background | `docker compose up -d` |
| Stop all services | `docker compose down` |
| View logs | `docker compose logs -f web` |
| Open a shell in the web container | `docker compose exec web bash` |
| Run migrations | `docker compose exec web python manage.py migrate` |
| Create superuser | `docker compose exec web python manage.py createsuperuser` |
| Run tests | `docker compose exec web python -m pytest -v` |
| Rebuild images | `docker compose up --build` |
| Wipe database (destructive) | `docker compose down -v` |

### Django management commands (local or inside Docker shell)

| Action | Command |
|---|---|
| Start dev server | `python manage.py runserver` |
| Apply migrations | `python manage.py migrate` |
| Create new migrations | `python manage.py makemigrations` |
| Open Django shell | `python manage.py shell` |
| Check for config errors | `python manage.py check` |
| Collect static files | `python manage.py collectstatic` |

---

## 13. Troubleshooting

### Docker Desktop is not running

**Symptom:** `docker compose up` fails with `error during connect` or `pipe not found`.

**Fix:** Open Docker Desktop and wait for the engine to start fully before retrying.

---

### Port 8000 is already in use

**Symptom:** `Bind for 0.0.0.0:8000 failed: port is already allocated`.

**Fix:** Stop whatever is using port 8000, or change the port in `docker-compose.yml`:
```yaml
ports:
  - "8001:8000"   # Use 8001 on your host instead
```

---

### Port 5432 is already in use

**Symptom:** The `db` container fails to start because a local PostgreSQL is already running on 5432.

**Fix:** Either stop your local PostgreSQL, or change the host port mapping in `docker-compose.yml`:
```yaml
ports:
  - "5433:5432"
```

---

### `POSTGRES_PASSWORD` not set error

**Symptom:** Django starts but crashes with `UndefinedValueError: POSTGRES_PASSWORD not found`.

**Fix:** Ensure your `.env` file exists in the project root and contains `POSTGRES_PASSWORD=`. The app will not start without it.

---

### Migrations fail with `relation does not exist`

**Symptom:** Django errors on startup about missing tables.

**Fix:** Run migrations manually:
```bash
docker compose exec web python manage.py migrate
```

---

### `ModuleNotFoundError` when running locally

**Symptom:** `ModuleNotFoundError: No module named 'django'` when running `python manage.py`.

**Fix:** Your virtual environment is not activated. Run:
```powershell
.venv\Scripts\Activate.ps1       # Windows PowerShell
source .venv/bin/activate         # macOS / Linux
```

---

### Tests connect to PostgreSQL instead of SQLite

**Symptom:** Tests fail with `could not translate host name "db"`.

**Fix:** Set the test settings module before running pytest:
```powershell
$env:DJANGO_SETTINGS_MODULE="config.settings.test"   # PowerShell
python -m pytest -v
```
