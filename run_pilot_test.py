"""
CEMS Pilot Test Script — Full end-to-end lifecycle test.

Exercises:
  - Student auth (student_id + DOB)
  - Admin auth (Django User + AdminProfile)
  - Voter eligibility (EligibleVoter / voter roll)
  - Election lifecycle: DRAFT → ACTIVE → CLOSED → PUBLISHED
  - Ballot casting (with double-vote prevention)
  - Results retrieval
  - Audit-log completeness
  - Brute-force lockout

Prerequisites:
  - PostgreSQL running with migrations applied
  - ``python manage.py generate_pilot_data --clear`` has been run

Run with:
    python run_pilot_test.py
"""
import json
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

import django
django.setup()

# Allow Django test client's default SERVER_NAME
from django.conf import settings as django_settings
if "testserver" not in django_settings.ALLOWED_HOSTS:
    django_settings.ALLOWED_HOSTS.append("testserver")

# Disable rate limiting so brute-force lockout test is isolated
django_settings.RATELIMIT_ENABLE = False

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from apps.accounts.models import AdminProfile, AdminRole, Student
from apps.audit.models import AuditLog
from apps.elections.models import (
    Candidate,
    Election,
    EligibleVoter,
    Position,
    VerificationRecord,
)
from apps.voting.models import Ballot

# ── Helpers ────────────────────────────────────────────────────────────────

PASS = "PASS"
FAIL = "FAIL"
results = []


def check(label, condition, detail=""):
    sym = PASS if condition else FAIL
    results.append((sym, label, detail))
    detail_str = f" | {detail}" if detail else ""
    print(f"[{sym}] {label}{detail_str}")


def make_client():
    return Client(enforce_csrf_checks=False)


def post(client, url, payload):
    return client.post(
        url,
        data=json.dumps(payload),
        content_type="application/json",
    )


def get(client, url):
    return client.get(url)


def admin_login(client, username="eb_head", password="pilot_admin_pass"):
    """Log in via the admin auth endpoint."""
    return post(client, "/api/admin/auth/login/", {
        "username": username,
        "password": password,
    })


def student_login(client, student):
    """Log in via the student auth endpoint."""
    return post(client, "/api/auth/login/", {
        "student_id": student.student_id,
        "date_of_birth": str(student.date_of_birth),
    })


# ── Setup ──────────────────────────────────────────────────────────────────
print("=== CEMS PILOT TEST ===\n")

# Ensure pilot data exists
election = Election.objects.first()
if not election:
    print("ERROR: No election found. Run 'python manage.py generate_pilot_data --clear' first.")
    sys.exit(1)

admin_profile = AdminProfile.objects.filter(role=AdminRole.ELECTORAL_BOARD_HEAD).first()
if not admin_profile:
    print("ERROR: No EB Head admin found. Run 'python manage.py generate_pilot_data --clear' first.")
    sys.exit(1)

# Grab test voter students (pick from those on the voter roll)
eligible_voter_entries = EligibleVoter.objects.filter(election=election).select_related("student")[:20]
if eligible_voter_entries.count() < 4:
    print("ERROR: Not enough eligible voters. Run 'python manage.py generate_pilot_data --clear' first.")
    sys.exit(1)

voter1 = eligible_voter_entries[0].student
voter2 = eligible_voter_entries[1].student
voter3 = eligible_voter_entries[2].student
brute_victim = eligible_voter_entries[10].student

# Reset failed_attempts/lock for all test voters
for v in [voter1, voter2, voter3, brute_victim]:
    v.failed_attempts = 0
    v.lock_until = None
    v.save(update_fields=["failed_attempts", "lock_until"])

# Fetch positions and candidates
pos_pres = (
    Position.objects.filter(election=election, category="executive")
    .exclude(title__icontains="Vice")
    .first()
)
pos_vp = Position.objects.filter(election=election, title__icontains="Vice").first()
pos_senate = Position.objects.filter(election=election, category="senate").first()

pres_cands = list(Candidate.objects.filter(position=pos_pres)[:5])
vp_cand = Candidate.objects.filter(position=pos_vp).first()
sen_cands = list(Candidate.objects.filter(position=pos_senate)[:3])

print(f"Admin user:     {admin_profile.user.username} ({admin_profile.display_name})")
print(f"Voter 1:        {voter1.student_id} | DOB: {voter1.date_of_birth}")
print(f"Voter 2:        {voter2.student_id} | DOB: {voter2.date_of_birth}")
print(f"Voter 3:        {voter3.student_id} | DOB: {voter3.date_of_birth}")
print(f"Election UUID:  {election.pk}")
print(f"Position (Pres): {pos_pres.pk} — {pos_pres.title}")
if pres_cands:
    print(f"  Candidate 1:   {pres_cands[0].pk} — {pres_cands[0].full_name}")
if len(pres_cands) > 1:
    print(f"  Candidate 2:   {pres_cands[1].pk} — {pres_cands[1].full_name}")
print(f"Position (VP):   {pos_vp.pk} — {pos_vp.title}")
print(f"  Candidate:     {vp_cand.pk} — {vp_cand.full_name}")
print(f"Position (Sen):  {pos_senate.pk} — {pos_senate.title}")
print(f"  Candidates:    {[c.full_name for c in sen_cands]}")
print()

# ── State Reset ────────────────────────────────────────────────────────────
print("--- RESET: Preparing clean pilot state ---")

# Reset election to DRAFT with a valid time window
election.status = "draft"
election.start_time = timezone.now() - timedelta(hours=1)
election.end_time = timezone.now() + timedelta(hours=24)
# Keep voter roll finalized (needed for DRAFT → ACTIVE transition)
election.save(update_fields=["status", "start_time", "end_time"])

# Clear pre-existing ballots for each test student (from prior runs)
for s in [voter1, voter2, voter3, brute_victim]:
    hashed = Ballot.hash_student_id(s.student_id, str(election.pk))
    deleted, _ = Ballot.objects.filter(election=election, hashed_student_id=hashed).delete()
    if deleted:
        print(f"  Cleared {deleted} ballot(s) for {s.student_id}")

print("  Reset complete — election is DRAFT, voter roll finalized, time window is valid\n")

# ── PHASE 1: Unauthenticated access ───────────────────────────────────────
print("--- PHASE 1: Unauthenticated Access ---")
anon = make_client()
for url in ["/api/elections/mine/", "/api/elections/current/", "/api/elections/status/"]:
    r = get(anon, url)
    check(f"Unauth GET {url}", r.status_code == 401, f"HTTP {r.status_code}")

r = get(anon, f"/api/elections/results/{election.pk}/")
check("Unauth GET results", r.status_code == 401, f"HTTP {r.status_code}")

r = post(anon, "/api/voting/cast/", {"election_id": str(election.pk), "selections": []})
check("Unauth POST /api/voting/cast/", r.status_code == 401, f"HTTP {r.status_code}")
print()

# ── PHASE 2: Invalid credentials ──────────────────────────────────────────
print("--- PHASE 2: Invalid Login ---")
c = make_client()
r = post(c, "/api/auth/login/", {"student_id": voter1.student_id, "date_of_birth": "1900-01-01"})
check("Login with wrong DOB rejected (401)", r.status_code == 401, f"HTTP {r.status_code}")

r = post(c, "/api/auth/login/", {"student_id": "9999-99999", "date_of_birth": "2000-01-01"})
check("Login with unknown student_id rejected (401)", r.status_code == 401, f"HTTP {r.status_code}")
print()

# ── PHASE 3: Admin login (Django User auth) ───────────────────────────────
print("--- PHASE 3: Admin Login ---")
admin_c = make_client()
r = admin_login(admin_c)
check("Admin login succeeds (200)", r.status_code == 200, str(r.json()))
print()

# ── PHASE 4: Non-admin cannot control lifecycle ───────────────────────────
print("--- PHASE 4: Non-Admin Cannot Control Election ---")
voter1_c = make_client()
r = student_login(voter1_c, voter1)
check("Voter 1 login succeeds", r.status_code == 200)

for endpoint in ["/api/admin/elections/start/", "/api/admin/elections/close/", "/api/admin/elections/publish/"]:
    r = post(voter1_c, endpoint, {"election_id": str(election.pk)})
    check(f"Student at {endpoint} returns 401", r.status_code == 401, f"HTTP {r.status_code}")
print()

# ── PHASE 5: Pre-active state ──────────────────────────────────────────────
print("--- PHASE 5: No Active Election While DRAFT ---")
r = get(voter1_c, "/api/elections/mine/")
check("/api/elections/mine/ returns empty list while DRAFT", r.status_code == 200, f"elections={r.json().get('elections', [])}")
if r.status_code == 200:
    check("No elections visible in DRAFT", len(r.json().get("elections", [])) == 0)

r = get(voter1_c, "/api/elections/current/")
check("No active election returns 404", r.status_code == 404, f"HTTP {r.status_code}")

r = get(voter1_c, f"/api/elections/results/{election.pk}/")
check("Results blocked while DRAFT (403)", r.status_code == 403, f"HTTP {r.status_code}")
print()

# ── PHASE 6: Start election (admin lifecycle) ─────────────────────────────
print("--- PHASE 6: Admin Starts Election ---")
r = post(admin_c, "/api/admin/elections/start/", {"election_id": str(election.pk)})
check("Admin starts election (200)", r.status_code == 200, str(r.json()))
election.refresh_from_db()
check("Election status is ACTIVE in DB", election.status == "active", election.status)
print()

# ── PHASE 7: Active state checks ──────────────────────────────────────────
print("--- PHASE 7: Active Election State ---")
r = get(voter1_c, "/api/elections/mine/")
check("/api/elections/mine/ shows active election", r.status_code == 200)
if r.status_code == 200:
    mine_elections = r.json().get("elections", [])
    check("At least one election visible", len(mine_elections) > 0, f"{len(mine_elections)} elections")
    if mine_elections:
        check("Election status is active", mine_elections[0].get("status") == "active")
        check("has_voted is False", mine_elections[0].get("has_voted") is False)

r = get(voter1_c, f"/api/elections/{election.pk}/ballot/")
check("Ballot endpoint returns 200", r.status_code == 200)
if r.status_code == 200:
    ballot_data = r.json()
    positions = ballot_data.get("positions", [])
    check("Ballot has positions", len(positions) > 0, f"{len(positions)} positions")
    check("has_voted is False on ballot", ballot_data.get("has_voted") is False)

r = get(voter1_c, "/api/elections/current/")
check("Active election visible via /current/ (200)", r.status_code == 200)
if r.status_code == 200:
    data = r.json()
    positions = data.get("election", {}).get("positions", [])
    check("Election has positions", len(positions) > 0, f"{len(positions)} positions")

r = get(voter1_c, "/api/elections/status/")
check("Voter 1 has_voted is False", r.status_code == 200 and r.json().get("has_voted") is False)

r = get(voter1_c, f"/api/elections/results/{election.pk}/")
check("Results blocked while ACTIVE (403)", r.status_code == 403, f"HTTP {r.status_code}")
print()

# ── PHASE 8: Cast ballot ──────────────────────────────────────────────────
print("--- PHASE 8: Cast Ballot ---")
selections = [
    {"position_id": str(pos_pres.pk), "candidate_id": str(pres_cands[0].pk)},
    {"position_id": str(pos_vp.pk), "candidate_id": str(vp_cand.pk)},
]
for s in sen_cands:
    selections.append({"position_id": str(pos_senate.pk), "candidate_id": str(s.pk)})

r = post(voter1_c, "/api/voting/cast/", {"election_id": str(election.pk), "selections": selections})
check("Voter 1 casts ballot (201)", r.status_code == 201, str(r.json()))

r = get(voter1_c, "/api/elections/status/")
check("Voter 1 has_voted is True", r.json().get("has_voted") is True)

r = get(voter1_c, "/api/elections/mine/")
if r.status_code == 200:
    mine_data = r.json().get("elections", [])
    if mine_data:
        check("has_voted reflected in /mine/", mine_data[0].get("has_voted") is True)
print()

# ── PHASE 9: Double vote ───────────────────────────────────────────────────
print("--- PHASE 9: Double Vote Prevention ---")
r = post(voter1_c, "/api/voting/cast/", {"election_id": str(election.pk), "selections": selections})
check("Double vote rejected (409)", r.status_code == 409, f"HTTP {r.status_code}")

audit_suspicious = AuditLog.objects.filter(event_type="suspicious_activity").count()
check("Suspicious activity logged in audit", audit_suspicious > 0, f"{audit_suspicious} entries")
print()

# ── PHASE 10: Second voter ──────────────────────────────────────────────────
print("--- PHASE 10: Second Voter Casts Ballot ---")
voter2_c = make_client()
student_login(voter2_c, voter2)
v2_selections = [{"position_id": str(pos_pres.pk), "candidate_id": str(pres_cands[1].pk)}] if len(pres_cands) > 1 else selections
r = post(voter2_c, "/api/voting/cast/", {"election_id": str(election.pk), "selections": v2_selections})
check("Voter 2 casts ballot (201)", r.status_code == 201, str(r.json()))
print()

# ── PHASE 11: Close election ───────────────────────────────────────────────
print("--- PHASE 11: Admin Closes Election ---")
r = post(admin_c, "/api/admin/elections/close/", {"election_id": str(election.pk)})
check("Admin closes election (200)", r.status_code == 200, str(r.json()))
election.refresh_from_db()
check("Election status is CLOSED in DB", election.status == "closed", election.status)
print()

# ── PHASE 12: Vote after close ─────────────────────────────────────────────
print("--- PHASE 12: Vote After Close Rejected ---")
voter3_c = make_client()
student_login(voter3_c, voter3)
r = post(voter3_c, "/api/voting/cast/", {"election_id": str(election.pk), "selections": selections})
check("Vote after close rejected (409)", r.status_code == 409, f"HTTP {r.status_code}")
print()

# ── PHASE 13: Invalid state transitions ───────────────────────────────────
print("--- PHASE 13: Invalid State Transitions ---")
r = post(admin_c, "/api/admin/elections/start/", {"election_id": str(election.pk)})
check("CLOSED -> ACTIVE rejected (409)", r.status_code == 409, f"HTTP {r.status_code}")

r = post(admin_c, "/api/admin/elections/close/", {"election_id": str(election.pk)})
check("CLOSED -> CLOSED rejected (409)", r.status_code == 409, f"HTTP {r.status_code}")
print()

# ── PHASE 14: Publish results ──────────────────────────────────────────────
print("--- PHASE 14: Publish Results ---")
r = post(admin_c, "/api/admin/elections/publish/", {"election_id": str(election.pk)})
check("Admin publishes results (200)", r.status_code == 200, str(r.json()))
election.refresh_from_db()
check("Election status is PUBLISHED in DB", election.status == "published", election.status)
print()

# ── PHASE 15: View results ─────────────────────────────────────────────────
print("--- PHASE 15: View Published Results ---")
r = get(voter1_c, f"/api/elections/results/{election.pk}/")
check("Results available after PUBLISHED (200)", r.status_code == 200, f"HTTP {r.status_code}")
if r.status_code == 200:
    data = r.json()
    positions = data.get("positions", [])
    check("Results have positions", len(positions) > 0, f"{len(positions)} positions")
    for p in positions:
        candidates_in_pos = p.get("results") or p.get("candidates", [])
        if candidates_in_pos:
            top = sorted(candidates_in_pos, key=lambda x: x.get("votes", 0), reverse=True)[0]
            check(
                f"Winner declared for '{p.get('position', p.get('title', '?'))}'",
                "votes" in top,
                f"{top.get('full_name', top.get('candidate', '?'))} - {top.get('votes')} votes",
            )
            break

# Also test /api/elections/mine/ shows published election
r = get(voter1_c, "/api/elections/mine/")
if r.status_code == 200:
    mine_data = r.json().get("elections", [])
    published_visible = any(e.get("status") == "published" for e in mine_data)
    check("Published election visible in /mine/", published_visible)
print()

# ── PHASE 16: Post-publish transition ─────────────────────────────────────
print("--- PHASE 16: Post-Publish Transitions Rejected ---")
r = post(admin_c, "/api/admin/elections/close/", {"election_id": str(election.pk)})
check("PUBLISHED -> CLOSED rejected (409)", r.status_code == 409, f"HTTP {r.status_code}")
print()

# ── PHASE 17: Brute-force lockout ─────────────────────────────────────────
print("--- PHASE 17: Brute-Force Lockout ---")
brute_victim.refresh_from_db()
brute_victim.failed_attempts = 0
brute_victim.lock_until = None
brute_victim.save()
bf_c = make_client()
for i in range(5):
    post(bf_c, "/api/auth/login/", {"student_id": brute_victim.student_id, "date_of_birth": "1900-01-01"})
brute_victim.refresh_from_db()
check("Account locked after 5 failed attempts", brute_victim.is_locked, f"failed_attempts={brute_victim.failed_attempts}")

r = post(bf_c, "/api/auth/login/", {"student_id": brute_victim.student_id, "date_of_birth": str(brute_victim.date_of_birth)})
check("Correct creds rejected while locked (401)", r.status_code == 401 and "locked" in r.json().get("error", "").lower())
print()

# ── PHASE 18: Admin auth checks ───────────────────────────────────────────
print("--- PHASE 18: Admin Auth Checks ---")
bad_admin_c = make_client()
r = admin_login(bad_admin_c, username="nonexistent", password="wrong")
check("Invalid admin login rejected (401)", r.status_code == 401, f"HTTP {r.status_code}")

# Non-EB-Head admin cannot do lifecycle
op_c = make_client()
r = admin_login(op_c, username="operator1")
check("Operator login succeeds", r.status_code == 200)
# Election is already published, but operator should get 403 regardless
r = post(op_c, "/api/admin/elections/start/", {"election_id": str(election.pk)})
check("Operator cannot start election (403)", r.status_code == 403, f"HTTP {r.status_code}")
print()

# ── PHASE 19: Audit log completeness ──────────────────────────────────────
print("--- PHASE 19: Audit Log Completeness ---")
audit_checks = [
    ("login_attempt", "Login attempts logged"),
    ("vote_cast", "Vote cast logged"),
    ("election_started", "Election start logged"),
    ("election_closed", "Election close logged"),
    ("results_published", "Results publish logged"),
    ("suspicious_activity", "Suspicious activity logged"),
]
for evt, label in audit_checks:
    count = AuditLog.objects.filter(event_type=evt).count()
    check(label, count > 0, f"{count} entries")

# Admin-specific audit events
admin_audit_checks = [
    ("admin_login_attempt", "Admin login attempts logged"),
]
for evt, label in admin_audit_checks:
    count = AuditLog.objects.filter(event_type=evt).count()
    check(label, count > 0, f"{count} entries")
print()

# ── SUMMARY ───────────────────────────────────────────────────────────────
passed = sum(1 for r in results if r[0] == PASS)
failed = sum(1 for r in results if r[0] == FAIL)

print("=" * 60)
print(f"PILOT TEST RESULT: {passed} passed, {failed} failed out of {passed + failed}")
print("=" * 60)

if failed > 0:
    print("\nFailed checks:")
    for sym, label, detail in results:
        if sym == FAIL:
            print(f"  [FAIL] {label} ({detail})")

sys.exit(0 if failed == 0 else 1)
