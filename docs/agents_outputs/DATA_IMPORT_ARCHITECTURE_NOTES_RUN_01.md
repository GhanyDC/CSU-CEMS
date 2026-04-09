# Data Import Architecture Notes — Run 01

**Date:** 2025-01-XX  
**Scope:** Registrar Import Batch system design, CSV processing pipeline, and voter roll generation workflow.

---

## 1. Architecture Overview

The Registrar Import Batch system provides a **two-step** data pipeline:

```
Registrar CSV → Import Batch → Assign to Election → Auto-generate Voter Roll
```

This separates the **system-level student dataset** (managed by the registrar's office) from the **election-specific voter roll** (managed by the electoral board).

### Why Two Steps?

1. **Reusability**: A single registrar batch can be assigned to multiple elections (e.g., campus-wide + college-level).
2. **Auditability**: The batch tracks when data was imported and by whom. The election tracks which batch it was generated from.
3. **Data Freshness**: New batches can be created each semester without affecting existing elections.
4. **Separation of Concerns**: Registrar data import is a system admin task; voter roll assignment is an election setup task.

---

## 2. Data Model

### `RegistrarImportBatch`

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `batch_name` | CharField(200) | Human-readable label (e.g., "AY 2024-2025 1st Semester") |
| `academic_year` | CharField(20) | Academic year (e.g., "2024-2025") |
| `semester` | CharField(20) | Semester (e.g., "1st", "2nd", "Summer") |
| `status` | CharField | `active` or `archived` |
| `student_count` | PositiveIntegerField | Count of students in batch |
| `created_at` | DateTimeField | Auto-set on creation |
| `updated_at` | DateTimeField | Auto-set on save |

### Relationship to Election

`Election.registrar_batch` — nullable FK to `RegistrarImportBatch`. Set when a batch is assigned. Used for provenance tracking.

### Relationship to Students

The batch import creates/updates `Student` records in `apps.accounts.models.Student`. Students are matched by `student_id` (unique). On import:
- **New students**: Created with all CSV fields
- **Existing students**: Updated with latest data (name, college, course, year)
- **Duplicates within CSV**: Skipped after first occurrence

---

## 3. CSV Format

### Voter Roll Import (per-election)

Minimal CSV for verification-only import:

```csv
student_id
2024-10001
2024-10002
```

### Registrar Batch Import (system-level)

Full student record CSV:

```csv
student_id,full_name,date_of_birth,college,course,year
2024-10001,Juan Dela Cruz,2003-05-15,College of Engineering,BSCE,3
2024-10002,Maria Santos,2002-11-20,College of Arts and Sciences,BS Psychology,2
```

Required column: `student_id`. Other columns are optional but recommended.

---

## 4. Security Measures

### CSV Processing (`_parse_csv_safely`)

1. **File size limit**: Configurable per endpoint (5 MB voter roll, 10 MB registrar batch)
2. **Row count limit**: 50,000 rows maximum (prevents memory exhaustion)
3. **Formula injection sanitization**: Cells starting with `=`, `+`, `-`, `@` are prefixed with `'` to prevent CSV injection in downstream Excel processing
4. **Generic error messages**: Parse errors are logged server-side; clients receive a generic "CSV is invalid" message (no internal detail leakage)
5. **Unicode validation**: Files must be valid UTF-8
6. **Column validation**: Required `student_id` column check

### Processing Integrity

- **Atomic operations**: Import transactions are atomic (all-or-nothing)
- **Audit trail**: All import actions logged via AuditLog
- **Permission checks**: Import requires `EB Head` or `Operator` role
- **Election state guard**: Voter roll import only allowed in Draft status

---

## 5. API Endpoints

### Batch Management

| Method | Path | Role | Description |
|--------|------|------|-------------|
| GET | `/api/admin/elections/setup/registrar-batches/` | EB Head, Operator | List all batches |
| POST | `/api/admin/elections/setup/registrar-batches/create/` | EB Head, Operator | Create new batch |
| POST | `/api/admin/elections/setup/registrar-batches/<bid>/import/` | EB Head, Operator | Import CSV data |
| POST | `/api/admin/elections/setup/<eid>/registrar-batch/assign/` | EB Head, Operator | Assign batch → election |

### Batch Create Request

```json
{
  "batch_name": "AY 2024-2025 1st Semester",
  "academic_year": "2024-2025",
  "semester": "1st"
}
```

### Batch Import Response

```json
{
  "success": true,
  "message": "Import complete: 150 created, 30 updated, 2 skipped.",
  "summary": {
    "created": 150,
    "updated": 30,
    "skipped": 2
  }
}
```

### Assign Batch Response

```json
{
  "success": true,
  "message": "Batch assigned. Voter roll generated: 180 verified, 5 unmatched."
}
```

---

## 6. Integration with Election Setup Flow

### Admin Panel UI Flow

1. **Batches View** (`view-batches`): Create and manage system-level batches. Import CSV files.
2. **Election Detail → Voter Roll Tab**: Assign an existing batch to the election. View college breakdown, unmatched records.
3. **Readiness Checklist**: "Voter roll imported" check verifies that `election.eligible_voters.count() > 0`.

### Workflow Sequence

```
1. Admin creates RegistrarImportBatch
2. Admin uploads CSV → _parse_csv_safely → RegistrarBatchService.import_students_to_batch
3. Student records created/updated in accounts.Student
4. Admin creates Election (Draft)
5. Admin assigns batch to election → RegistrarBatchService.assign_batch_to_election
6. System auto-generates VerificationRecord entries for each student in batch
7. College breakdown computed, unmatched records flagged
8. Admin reviews voter roll in Voter Roll tab
9. Admin finalizes election → moves to Active
```

---

## 7. Future Considerations

- **Incremental imports**: Currently replaces all data. Could add append-only mode.
- **Batch diffing**: Compare two batches to identify added/removed/changed students.
- **Automated scheduling**: Integrate with registrar's system for automatic periodic imports.
- **Export**: Add CSV export endpoint for audit purposes.
