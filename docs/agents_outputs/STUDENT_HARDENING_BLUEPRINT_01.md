# STUDENT HARDENING BLUEPRINT 01

**Date:** 2026-04-10  
**Status:** Implemented and tested

---

## 1. Final Student-Side Page Structure

| Page | Route | Template | Auth Required | Purpose |
|------|-------|----------|---------------|---------|
| Login | `/` | `login.html` | No | Student ID + DOB authentication |
| Dashboard | `/dashboard/` | `dashboard.html` | Yes | Eligible elections, status, navigation |
| Ballot | `/ballot/` | `ballot.html` | Yes | Cast vote with card-based UI |
| Results | `/results/` | `results.html` | Yes | View published election results |

### API Endpoints Used by Student Pages

| Endpoint | Method | Page | Purpose |
|----------|--------|------|---------|
| `/api/auth/login/` | POST | Login | Authenticate student |
| `/api/auth/logout/` | POST | All | End session |
| `/api/elections/mine/` | GET | Dashboard, Ballot, Results | Get eligible elections |
| `/api/elections/<id>/ballot/` | GET | Ballot | Get ballot structure |
| `/api/voting/cast/` | POST | Ballot | Submit ballot |
| `/api/elections/results/<id>/` | GET | Results | Get published results |

---

## 2. Final Ballot State Model

### Architecture: Single Source of Truth

```
ballotState: Map<positionId: string, PositionState>

PositionState = {
    candidates: Set<candidateId: string>,
    abstain: boolean
}
```

### State Update Functions

| Function | Input | Behavior |
|----------|-------|----------|
| `initBallotState(positions)` | API response positions array | Creates empty state for each position |
| `selectCandidate(posId, candId)` | Position and candidate IDs | Updates candidate set, clears abstain |
| `toggleAbstain(posId)` | Position ID | Toggles abstain, clears candidates if enabling |
| `syncUI()` | None (reads ballotState) | Renders all visual elements from state |
| `updateSummary()` | None (reads ballotState) | Builds review section HTML |

### State Flow Diagram

```
User clicks card
       │
       ▼
selectCandidate() or toggleAbstain()
       │
       ▼
  Update ballotState Map
       │
       ▼
     syncUI()
       │
       ├── Update card .selected classes
       ├── Update abstain card .selected class
       ├── Update counter badges
       └── updateSummary()
              │
              ├── Build review HTML from state
              └── Enable/disable submit button
```

### Submit Payload

Built exclusively from `ballotState`:

```json
{
    "election_id": "<uuid>",
    "selections": [
        {"position_id": "<uuid>", "candidate_id": "<uuid>"},
        ...
    ]
}
```

- Only candidate selections are sent (not abstain flags)
- Positions where student abstained have zero selections
- Backend computes abstain count as `total_ballots - position_participation`
- Empty selections array (all-abstain) is blocked client-side and server-side

---

## 3. Abstain Card Behavior Rules

### Visual Treatment

- Abstain is rendered as a **card** in the same grid as candidate cards
- Dashed border (distinguishes from candidate cards)
- Yellow/gold color scheme when selected (vs green for candidates)
- Dash-circle icon (vs person icon for candidates)
- Same card dimensions and responsive behavior as candidate cards

### Interaction Rules

| Scenario | Single-Select Position | Multi-Select Position |
|----------|----------------------|----------------------|
| Select candidate | Deselects any other candidate + clears abstain | Adds to selection set + clears abstain |
| Deselect candidate | Clears selection | Removes from set |
| Select abstain | Clears all candidates | Clears all candidates |
| Deselect abstain | Returns to empty state | Returns to empty state |
| Max selections reached | N/A (only 1) | Toast warning, selection blocked |
| Candidate + Abstain coexist | **Never** — mutually exclusive | **Never** — mutually exclusive |

### Counter Badge Behavior

| State | Badge Text | Badge Style |
|-------|-----------|-------------|
| No selection | `0 / N` | `badge-draft` (gray) |
| Candidates selected | `K / N` | `badge-active` (green) |
| Abstain selected | `Abstain` | `badge-closed` (red) |

### Review Summary Representation

| State | Review Display |
|-------|---------------|
| Candidates selected | Green badges with candidate names |
| Abstain | Red badge: "⊘ Abstain" |
| No selection | Gray text: "⚠ No selection" |

---

## 4. Review/Submit Behavior Rules

### Review Section

- Shows each position as a row
- Position title on left, selection display on right
- Responsive: stacks vertically on mobile
- Updates in real-time as ballotState changes
- No separate state — derived entirely from `ballotState`

### Submit Button

| Condition | Button State |
|-----------|-------------|
| No selections and no abstains | **Disabled** |
| At least one candidate selected | **Enabled** |
| At least one abstain (but not all) | **Enabled** |
| All positions abstained | **Enabled** client-side, but **blocked** on submit (must vote for at least one) |

### Submit Flow

1. Build selections from `ballotState`
2. Check: if zero selections → toast "must vote for at least one candidate"
3. Native confirm dialog
4. Disable button + show spinner
5. POST to `/api/voting/cast/`
6. Success → show modal (election name, timestamp, ballot ID)
7. 409 → "already submitted" message + auto-redirect
8. 401 → session expired banner
9. Other error → toast + re-enable button

### Submit Hardening

- Button disabled immediately (prevents double-tap)
- Spinner shown during network call
- Re-enabled only on recoverable errors
- 409 shows friendly message (not raw error)
- Form hidden after successful submission
- Success modal uses `data-bs-backdrop="static"` (can't click away)

---

## 5. Dashboard Visibility Rules

### Election Visibility

| Election State | Student Sees | Action Available |
|----------------|-------------|-----------------|
| Draft | **Hidden** | — |
| Active (not voted) | **Visible** | "Vote Now" button |
| Active (voted) | **Visible** | "Submitted" indicator |
| Closed | **Hidden** | — |
| Published | **Visible** | "View Results" button |

### College Scoping

- Campus elections: visible to all students on the voter roll
- College elections: visible only if `election.college == student.college`
- Even if accidentally on voter roll for wrong college, college mismatch blocks visibility

### Status Cards

- Election Status: shows count of active elections
- Vote Status: "All Voted" / "Partially Voted" / "Not Yet"
- Time Remaining: countdown to first active election end time

### Empty States

- No eligible elections: centered message with EB contact suggestion
- Session expired: toast + auto-redirect to login

---

## 6. College Representative Filtering Rules

### Backend Enforcement (Canonical)

In `election_ballot()` view:

```python
if pos.category == Position.Category.HOUSE_COLLEGE and election.is_campus:
    candidates_qs = candidates_qs.filter(college=student.college)
    if not candidates_qs.exists():
        continue  # Skip position entirely
```

### Rules

1. `HOUSE_COLLEGE` positions in **campus** elections filter by `student.college`
2. If no candidates match the student's college, the position is **not shown at all**
3. `EXECUTIVE`, `SENATE`, `HOUSE_PARTY` positions shown to all eligible voters
4. College elections show all positions to voters of that college (no cross-college access)
5. Filtering is **backend-enforced** — the API never returns other-college candidates
6. Frontend renders exactly what the API returns (no additional filtering needed)

### Test Coverage

- `TestCollegeRepFiltering.test_college_rep_only_shows_own_college_candidates`
- `TestCollegeRepFiltering.test_college_rep_position_hidden_if_no_candidates`
- `TestCollegeRepFiltering.test_campus_wide_positions_shown_to_all`

---

## 7. Confirmation/Results Access Rules

### Confirmation (after successful submission)

- Success modal with:
  - Green checkmark icon
  - "Vote Submitted!" heading
  - Election name
  - Submission timestamp
  - Ballot ID
  - Privacy notice: "Your vote is anonymous and cannot be changed"
  - "Back to Dashboard" button
- Ballot form hidden behind modal
- Modal cannot be dismissed by clicking outside (`data-bs-backdrop="static"`)
- No full vote details shown (privacy on shared devices)

### Results Access

| Condition | Access |
|-----------|--------|
| Election not Published | 403 "Results not yet published" |
| Student not on voter roll | 403 "Not eligible" |
| Election Published + Student eligible | 200 with full results |
| Anonymous user | 401 |

### Results Data Shown

- Election name
- Total ballots, positions, candidates, turnout percentage
- Per-position: candidate results with vote bars, winner badge, photos
- Abstain counts per position
- 50%+1 threshold information
- Category badges (Executive, Senate, College Rep, Party-List)
