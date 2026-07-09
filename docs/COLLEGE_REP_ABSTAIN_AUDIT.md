# College Representative Abstain Count Audit

Date: 2026-07-09

## Summary

Status: PASS

The college representative abstain-count bug was verified against the result
aggregation flow. Campus College Representative positions now use a
college-scoped ballot denominator, so a CICS voter is not counted as abstaining
from HSS or other college representative seats.

## Verified Behavior

- A CICS student sees only the CICS College Representative position on the
  ballot.
- A CICS vote for the CICS representative creates participation for the CICS
  representative seat only.
- That same CICS ballot does not increase HSS representative participation,
  total ballots, or abstain count.
- If the CICS student votes only for a campus-wide position, the CICS
  representative seat records one CICS abstain and the HSS representative seat
  remains unaffected.
- Election-level `total_ballots` remains campus-wide; per-position
  `total_ballots` is scoped only for campus College Representative seats.

## Smoke Test

An isolated smoke test ran in a disposable Django test database. It created a
campus election with President, HSS Representative, and CICS Representative
positions; added CICS and HSS eligible voters; fetched the CICS ballot; cast
ballots; and computed results.

Result:

```text
SMOKE PASS
visible_reps= ['College Representative - Information and Computing Sciences']
scenario_1= CICS rep participation 1/1, HSS rep abstain 0/0
scenario_2= CICS president-only ballot makes CICS rep abstain 1/1, HSS rep abstain 0/0
```

A Docker-backed smoke test was also run against the local Compose environment
after restarting the `web` service. It used the running web container and local
Postgres database, exercised the ballot and cast-vote API endpoints via Django's
request stack, verified the same CICS/HSS scenarios, and cleaned up all
temporary records.

Result:

```text
DOCKER SMOKE PASS
visible_reps= ['College Representative - Information and Computing Sciences']
scenario_1= CICS rep participation 1/1, HSS rep abstain 0/0
scenario_2= CICS president-only ballot makes CICS rep abstain 1/1, HSS rep abstain 0/0
cleanup= {'elections': 0, 'students': 0}
```

## Regression Tests

Commands run:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test apps.elections.tests.CollegeRepresentativeScopeTests --settings=config.settings.test
.\.venv\Scripts\python.exe manage.py test apps.accounts apps.elections apps.voting apps.audit --settings=config.settings.test
git diff --check
```

Results:

- Django system check: PASS
- CollegeRepresentativeScopeTests: PASS, 7 tests
- Full regression suite: PASS, 26 tests
- Diff whitespace check: PASS, with only Git's existing CRLF conversion warnings
- Docker service smoke: PASS, `web` and `db` healthy

## Audit Notes

- The fix is isolated to `ResultService` result aggregation and does not change
  ballot rendering, vote submission, database schema, URLs, or public endpoint
  shapes.
- The denominator source is `HybridElectionService.compute_turnout_breakdown`,
  which already maps anonymous online ballots back to eligible voters by hashed
  student ID and groups them by `EligibleVoter.college_snapshot`.
- Current ballot validation still rejects cross-college representative
  selections before a ballot is stored.
- Hybrid combined results still hide position-level abstain counts because
  onsite aggregate imports do not include per-position abstention data. The
  scoped per-position `total_ballots` remains available for consistency.
- Historical malformed data with cross-college representative selections would
  still appear in raw candidate tallies. The existing College Representative
  post-audit report remains the validated source for excluding such invalid
  cross-college votes.
- The first in-container API smoke attempt used Django's default test host
  `testserver`, which local settings reject. The final run used
  `HTTP_HOST=localhost`, matching the local `ALLOWED_HOSTS`.
