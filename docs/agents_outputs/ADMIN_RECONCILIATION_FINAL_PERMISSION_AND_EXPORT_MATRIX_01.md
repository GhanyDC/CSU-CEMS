# Admin Reconciliation — Final Permission & Export Matrix

**Date**: 2026-04-10
**Authority**: This matrix is the definitive role-permission reference for CEMS admin.

---

## 1. Active Admin Roles

| Role | Constant | Status |
|------|----------|--------|
| Electoral Board Head | `ELECTORAL_BOARD_HEAD` | **Active** — full admin authority |
| Operator | `ELECTORAL_BOARD_OPERATOR` | **Active** — setup assistant, restricted |
| Tally Watcher | `TALLY_WATCHER` | **Active** — read-only monitoring |
| Auditor | `AUDITOR` | **Model-only** — denied on all admin endpoints (403) |
| Technical Support | `TECHNICAL_SUPPORT` | **Model-only** — denied on all admin endpoints (403) |

---

## 2. Role Permissions by Area

### Election Management

| Action | EB Head | Operator | Tally Watcher |
|--------|---------|----------|---------------|
| List elections | ✅ | ✅ | ✅ |
| View election detail | ✅ | ✅ | ✅ |
| Create campus election | ✅ | ✅ | ❌ |
| Create college elections | ✅ | ✅ | ❌ |
| Delete election (Draft) | ✅ | ✅ | ❌ |
| Upload election banner | ✅ | ✅ | ❌ |

### Position Management

| Action | EB Head | Operator | Tally Watcher |
|--------|---------|----------|---------------|
| Create position | ✅ | ❌ | ❌ |
| Edit position | ✅ | ❌ | ❌ |
| Delete position | ✅ | ❌ | ❌ |
| Reorder positions (Drag) | ✅ Draft only | ❌ | ❌ |

### Candidate Management

| Action | EB Head | Operator | Tally Watcher |
|--------|---------|----------|---------------|
| Add candidate | ✅ Draft only | ✅ Draft only | ❌ |
| Edit candidate | ✅ Draft only | ✅ Draft only | ❌ |
| Delete (soft) candidate | ✅ Draft only | ✅ Draft only | ❌ |
| Upload candidate photo | ✅ Draft only | ✅ Draft only | ❌ |

### Voter Roll

| Action | EB Head | Operator | Tally Watcher |
|--------|---------|----------|---------------|
| View voter roll summary | ✅ | ✅ | ✅ |
| Import verification CSV | ✅ | ✅ | ❌ |
| Generate voter roll | ✅ | ✅ | ❌ |
| **Finalize voter roll** | ✅ | **❌** | ❌ |

### Registrar Batches

| Action | EB Head | Operator | Tally Watcher |
|--------|---------|----------|---------------|
| List batches | ✅ | ✅ | ✅ |
| Create batch | ✅ | ✅ | ❌ |
| Import batch CSV | ✅ | ✅ | ❌ |
| Delete batch | ✅ | ❌ | ❌ |
| Assign batch to election | ✅ | ✅ | ❌ |

### Lifecycle Transitions

| Action | EB Head | Operator | Tally Watcher |
|--------|---------|----------|---------------|
| Start election (Draft → Active) | ✅ | ❌ | ❌ |
| Close election (Active → Closed) | ✅ | ❌ | ❌ |
| Publish results (Closed → Published) | ✅ | ❌ | ❌ |

### Monitoring & Readiness

| Action | EB Head | Operator | Tally Watcher |
|--------|---------|----------|---------------|
| View readiness checklist | ✅ | ✅ | ✅ |
| View turnout data | ✅ | ✅ | ✅ |
| View tally data (see §3) | ✅ | ✅ redacted | ✅ role-aware |

---

## 3. Tally Visibility by Election State

| State | EB Head | Operator | Tally Watcher |
|-------|---------|----------|---------------|
| **Draft** | ❌ 403 | ❌ 403 | ❌ 403 |
| **Active** | ✅ Full live tally | ⚠️ Participation summary only (redacted) | ⚠️ Participation summary only (redacted) |
| **Closed** | ✅ Full tally | ⚠️ Participation summary only (redacted) | ✅ Full tally |
| **Published** | ✅ Full tally | ⚠️ Participation summary only (redacted) | ✅ Full tally |

### What "redacted" means

When `redacted: true` is returned:
- Per-candidate `votes` field is removed
- `winner` field is removed per position
- `status` field is removed per position
- `redacted_reason` explains why

Still available in redacted response:
- Position names, categories, candidate names, parties, photos
- `abstain_count`, `position_participation`, `total_ballots` per position
- `total_eligible`, `turnout_percentage` at top level

---

## 4. Export Permissions by Role and State

| Export | EB Head | Operator | Tally Watcher | Earliest State |
|--------|---------|----------|---------------|----------------|
| Turnout CSV | ✅ | ✅ | ✅ | Active |
| Turnout Text (clipboard) | ✅ | ✅ | ✅ | Active |
| **Tally CSV** | ✅ | **❌** | ✅ | **Closed** |
| **Participation CSV** | ✅ | **❌** | **❌** | **Closed** |
| **Ballot Audit CSV** | ✅ | **❌** | **❌** | **Closed** |

### Export State Restrictions

- **Draft**: All exports return 403
- **Active**: Only turnout exports available
- **Closed/Published**: Tally and internal exports available (role-permitting)

### Export Content Summary

| Export | Contains | Does NOT Contain |
|--------|----------|-----------------|
| Turnout CSV | total_eligible, total_voted, turnout_percent | Per-candidate data |
| Turnout Text | Human-readable turnout summary | Per-candidate data |
| Tally CSV | Per-position, per-candidate votes, percentages, abstain counts | Student identifiers |
| Participation CSV | student_id, voted (yes/no), timestamp | Vote choices |
| Ballot Audit CSV | truncated ballot hash, position, candidate, timestamp | Real student IDs |

### Audit Logging

All export downloads create an `EXPORT_GENERATED` audit event recording:
- Export type
- Admin user who performed the export
- Election ID
- Timestamp

---

## 5. Positions & Candidates Tab — State-Aware Behavior

| State | Behavior |
|-------|----------|
| **Draft** | Full edit mode. EB Head: position CRUD + drag reorder + candidate CRUD + photo upload. Operator: candidate CRUD + photo upload. TW: read-only roster. |
| **Active** | Locked. Monitoring mode. Shows per-position participation, abstain count. EB Head sees per-candidate live vote counts. Operator/TW see participation only. |
| **Closed** | Review mode. EB Head and TW see full per-candidate vote counts. Operator sees participation only. |
| **Published** | Same as Closed. |

---

## 6. UI Export Button Visibility

| Button | Condition |
|--------|-----------|
| Turnout CSV | Always shown when `status !== 'draft'` |
| Turnout Text | Always shown when `status !== 'draft'` |
| Tally CSV | `(is_eb_head OR is_read_only) AND (closed OR published)` |
| Participation CSV | `is_eb_head AND (closed OR published)` |
| Ballot Audit CSV | `is_eb_head AND (closed OR published)` |
| Info message | Shown during Active when tally exports not yet available |
