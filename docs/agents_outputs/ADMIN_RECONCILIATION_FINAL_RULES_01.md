# Admin Reconciliation — Final Reconciled Rules

**Date**: 2026-04-10
**Authority**: This document is the post-reconciliation canonical ruleset for the CEMS Admin Panel.

---

## Rule 1 — Tab Structure

The admin panel has exactly **4 tabs**:

1. **Overview** — Election metadata, turnout, readiness (Draft), export buttons
2. **Positions & Candidates** — Roster, monitoring data (Active/Closed/Published), editing (Draft only)
3. **Voter Roll** — Import pipeline, metrics, college breakdown, finalization
4. **Lifecycle** — State transitions (EB Head only)

There is **no** Monitoring tab. There is **no** Readiness tab. Monitoring data is integrated into Overview (aggregate) and Positions & Candidates (per-position). Readiness is a section within Overview that appears only during Draft.

---

## Rule 2 — Active Admin Roles

| Role | Code | Status |
|------|------|--------|
| EB Head | `EB_HEAD` | Active — Full access |
| Operator | `OPERATOR` | Active — Setup-scoped |
| Tally Watcher | `TALLY_WATCHER` | Active — Read-only |

**Inactive roles** (defined in model, always denied 403):
- `AUDITOR` — Post-election audit (not yet implemented)
- `TECHNICAL_SUPPORT` — System support (not yet implemented)

---

## Rule 3 — Tally Visibility by Role and State

| State | EB Head | Operator | Tally Watcher |
|-------|---------|----------|---------------|
| Draft | 403 | 403 | 403 |
| Active | Full per-candidate data | Redacted (participation only) | Redacted (participation only) |
| Closed | Full per-candidate data | Redacted (participation only) | Full per-candidate data |
| Published | Full per-candidate data | Redacted (participation only) | Full per-candidate data |

**Redacted** means: the API returns `"redacted": true`, includes `total_ballots` and per-position `position_participation` and `abstain_count`, but does NOT include per-candidate `votes` fields. The Positions tab renders only participation bars for redacted data and full vote/percentage displays for full data.

**Operator never sees per-candidate votes** in any state. This is a deliberate security rule.

---

## Rule 4 — Export Permissions

| Export | EB Head | Operator | TW |
|--------|---------|----------|----|
| Turnout CSV | Active, Closed, Published | Active, Closed, Published | Active, Closed, Published |
| Turnout Text | Active, Closed, Published | Active, Closed, Published | Active, Closed, Published |
| Tally CSV | Closed, Published | Never | Closed, Published |
| Participation CSV | Closed, Published | Never | Never |
| Ballot Audit CSV | Closed, Published | Never | Never |

Exports are **not** available during Draft for any role.

---

## Rule 5 — Position & Candidate Management

| Action | EB Head | Operator | TW |
|--------|---------|----------|----|
| Add Position | Draft only | Never | Never |
| Edit Position | Draft only | Never | Never |
| Delete Position | Draft only | Never | Never |
| Reorder Positions (drag) | Draft only | Never | Never |
| Add Candidate | Draft only | Draft only | Never |
| Edit Candidate | Draft only | Draft only | Never |
| Delete Candidate | Draft only | Draft only | Never |

All editing controls are hidden when the election is not in Draft. Operator has no position-level management but can manage candidates under existing positions.

---

## Rule 6 — Lifecycle Transitions

| Transition | Who Can Do It |
|------------|---------------|
| Draft → Active | EB Head only |
| Active → Closed | EB Head only |
| Closed → Published | EB Head only |
| Reverse any state | Nobody — transitions are one-way |

Operator and TW see a read-only lifecycle timeline. Only EB Head sees action buttons.

---

## Rule 7 — Voter Roll

- Import pipeline: Link Batch → Import Students → Generate Voter Roll → Finalize
- Only EB Head can finalize the voter roll
- Operator can create registrar batches and trigger import steps
- TW cannot modify voter roll
- After finalization: no further changes allowed, green confirmation banner displayed
- College breakdown table shows approved count and share per college
- Voter eligibility uses `voter_approved=True` for casting access

---

## Rule 8 — Abstain Handling

- Every position shows an "Abstain" checkbox on the ballot
- Abstain is mutually exclusive with candidate selection for a given position
- Submitting abstain for ALL positions is blocked ("must vote for at least one candidate")
- Abstain votes are counted and stored as `abstain_count` per position in results
- Admin tally displays abstain count alongside candidate votes

---

## Rule 9 — Candidate Photos

- Photos are optional. Candidates without photos get a Bootstrap Icons fallback (person-circle)
- Photos stored at `media/candidate_photos/`
- Admin panel shows photo in candidate cards; ballot page shows photo in candidate rows
- No upload validation beyond Django's ImageField (type check + size limit via django-resized if configured)

---

## Rule 10 — College Representative Filtering

- Positions with `position_type = COLLEGE_REP` are filtered per voter's college
- Student sees only candidates for their own college
- Backend filtering in `election_ballot` view: `candidates = candidates.filter(college=voter.college)`
- Campus-wide positions (`CAMPUS_WIDE`) shown to all voters regardless of college

---

## Enforcement

These rules are enforced at three layers:

1. **Backend**: Decorators (`@eb_head_required`, `@setup_roles_required`), service-level checks in `views.py`, `admin_views.py`, `export_views.py`
2. **Template**: Conditional rendering in `admin_panel.html` based on `adminUser.is_eb_head`, `adminUser.is_operator`, `adminUser.is_read_only`, and election `status`
3. **Tests**: 498 automated tests covering role-based access, tally visibility, export permissions, lifecycle transitions, and ballot behavior (`tests/test_reconciliation.py` + existing test files)

---

## Document Lineage

This document supersedes any conflicting statements in:
- `SYSTEM_SOURCE_OF_TRUTH.md`
- `IMPLEMENTATION_ROADMAP.md`
- `KNOWN_DECISIONS_COMPACT.md`
- All prior `agents_outputs/*.md` files

When conflicts exist, this document wins.
