# Style & Data Notes — Final Admin Panel Run

**Date**: 2026-04-10

---

## 1. Branding & Style Status

### Existing Implementation (No Changes Needed)

| Element | Status | Details |
|---------|--------|---------|
| Colour palette | ✅ Applied | Maroon `#800000` and Gold `#FFD700` via CSS variables in `cems.css` |
| Typography | ✅ Applied | Inter font loaded from Google Fonts |
| Icons | ✅ Applied | Bootstrap Icons 1.11.3 |
| Framework | ✅ Applied | Bootstrap 5.3.3 |
| Dark mode | ✅ Applied | Dark background (`#111`), maroon header gradient, gold accents |
| Cards | ✅ Applied | Semi-transparent black cards with rounded corners |
| Admin panel tabs | ✅ Applied | 5-tab layout (Overview, Positions, Voter Roll, Lifecycle, Monitoring) |

### New UI Elements — Style Conformance

| Element | Template | Style Applied |
|---------|----------|---------------|
| Exports card | `admin_panel.html` → `renderOverview()` | Same card styling as existing overview cards. Buttons use Bootstrap `btn-outline-warning` (gold) and `btn-outline-light` |
| Position reorder arrows | `admin_panel.html` → `renderPositions()` | `btn-sm btn-outline-warning` — matches existing action buttons |
| Abstain checkbox | `ballot.html` | `form-check-input` Bootstrap class, inherits existing input styling |
| Abstain badge in summary | `ballot.html` | Uses existing `badge bg-secondary` class |
| Abstain count in results | `results.html` | `text-muted` with `small` text, matches existing result detail styling |
| Reorder hint text | `admin_panel.html` | `text-muted small mt-2` — consistent with other help text |

---

## 2. Data Flow: Abstain Computation

Abstain is **computed at query time**, not stored as a model field.

```
Election has N total ballots
Position P has M ballots with at least one selection

abstain_count = N - M
```

Implementation: `apps/elections/services.py` → `_compute_position_result()`

- `total_ballots` = count of all `Ballot` objects for the election
- `position_participation` = count of distinct `BallotItem` objects for the position
- `abstain_count` = `total_ballots` - `position_participation`

**Key design decision**: No `Abstain` model or `is_abstain` field. A voter who opens the ballot but does not select any candidate for a position is counted as abstaining for that position. The client-side abstain checkbox simply prevents selection — it does not send any additional data.

---

## 3. Export Data Formats

### Turnout CSV
```csv
metric,value
total_eligible,150
total_voted,87
turnout_percent,58.0
```

### Turnout Text (JSON response)
```json
{
  "text": "Turnout: 87/150 (58.0%)\nGenerated: 2026-04-10 14:30 UTC"
}
```

### Tally CSV
```csv
position,candidate,votes,percentage,abstain_count
President,Alice Smith,45,51.7,5
President,Bob Jones,42,48.3,5
Vice President,Carol White,50,57.5,3
Vice President,Dave Brown,37,42.5,3
```

### Participation CSV (EB Head only)
```csv
student_id,voted,timestamp
2021-00001,yes,2026-04-10T09:15:00Z
2021-00002,yes,2026-04-10T09:22:00Z
2021-00003,no,
```

### Ballot Audit CSV (EB Head only)
```csv
ballot_hash,position,candidate,timestamp
a1b2c3d4,President,Alice Smith,2026-04-10T09:15:00Z
a1b2c3d4,Vice President,Carol White,2026-04-10T09:15:00Z
e5f6g7h8,President,Bob Jones,2026-04-10T09:22:00Z
```

The `ballot_hash` is a truncated SHA-256 hash of the ballot UUID — it allows verification of ballot integrity without revealing student identity.

---

## 4. Position Reorder Data Flow

1. Client calls `POST /api/admin/elections/{id}/positions/reorder/` with body: `{"order": ["uuid1", "uuid2", "uuid3"]}`
2. Server validates: election is Draft, user is EB Head, all UUIDs belong to the election
3. Server sets `position.order = index + 1` (1-based)
4. Client refreshes election data via `loadElection()`

---

## 5. Known Limitations & Future Work

| Area | Limitation | Suggested Resolution |
|------|-----------|---------------------|
| College rep filtering | Server-side filter works; frontend dropdown for college selection not yet added | Add `<select>` in ballot.html to filter visible positions by college |
| Export formats | Only CSV and clipboard text | Consider PDF report generation for official use |
| Photo storage | Photos stored in `media/election_banners/` | Consider separate `media/candidate_photos/` path |
| Reorder UX | Full page refresh after reorder | Use optimistic UI update or partial refresh |
| Abstain threshold | No minimum turnout or abstain threshold enforced | May want configurable threshold for election validity |
| Bulk candidate import | Not implemented | Add CSV import for candidates per position |
| Real-time updates | Admin monitoring uses polling | Consider WebSocket/SSE for live turnout dashboard |

---

## 6. Frozen Rules Preserved

All changes in this run respect the frozen rules established in `docs/KNOWN_DECISIONS_COMPACT.md`:

- ✅ Election lifecycle: one-way DRAFT → ACTIVE → CLOSED → PUBLISHED
- ✅ No ballot modification after submission
- ✅ Session-based student auth (student_id + birthdate)
- ✅ Anonymity guaranteed — no student↔ballot link in exports
- ✅ PostgreSQL in production, SQLite for tests
- ✅ Single-college per election scope
