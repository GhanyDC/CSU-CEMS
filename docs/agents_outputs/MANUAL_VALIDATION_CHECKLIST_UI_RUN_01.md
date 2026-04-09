# Manual Validation Checklist — UI/UX, Imports, Media & Filter Fix

**Date:** 2025-01-XX  
**Purpose:** Step-by-step manual testing guide for all changes in this run.

---

## Prerequisites

1. Run `python manage.py migrate` (migration 0005)
2. Run `python manage.py generate_pilot_data` for test data
3. Ensure `Pillow` is installed (`pip install -r requirements/base.txt`)
4. Start dev server: `python manage.py runserver`

---

## A. Visual Design System Verification

### A1. Student Login Page (`/`)
- [ ] Page background uses light gray (`--cems-bg`)
- [ ] Card uses `.cems-card` styling (white, rounded, shadow)
- [ ] Brand icon "E" in maroon square at top
- [ ] "CEMS" title in maroon color
- [ ] Sign In button uses maroon (`btn-cems-primary`)
- [ ] Form inputs have rounded borders

### A2. Admin Login Page (`/admin-login/`)
- [ ] Same card layout as student login
- [ ] "CEMS Admin" title in maroon
- [ ] Brand icon matches student login
- [ ] "Admin Sign In" button in maroon
- [ ] "Back to student login" link present

### A3. Student Dashboard (`/dashboard/`)
- [ ] Navbar: maroon background, brand icon, nav links, logout button
- [ ] User name displayed in navbar (desktop)
- [ ] Admin gear icon visible if user is admin
- [ ] Metric cards row: 4 metric-card boxes with colored values
- [ ] Election cards below: each with status badge, vote badge, time badge
- [ ] Status badges use correct colors (draft=muted, active=teal, closed=amber, published=green)

### A4. Ballot Page (`/ballot/`)
- [ ] Navbar consistent with dashboard
- [ ] Back link to dashboard (maroon colored arrow)
- [ ] Each position renders inside a `.cems-card`
- [ ] Candidate cards show photo (circular, 48×48) or placeholder icon
- [ ] Platform text displays below candidate name
- [ ] Selection counter badge updates on click
- [ ] Selected candidates have highlight border

### A5. Results Page (`/results/`)
- [ ] Metric cards: Total Ballots (maroon), Positions (green), Candidates (blue), Turnout (gold)
- [ ] Each position in a `.cems-card` with numbered badge
- [ ] Category badges: Executive (red bg), Senate (blue bg), College Rep (green bg), Party-List (amber bg)
- [ ] Candidate results show circular photo or placeholder
- [ ] College info displayed for each candidate
- [ ] Results bars: winner in green, others in maroon
- [ ] Trophy icon on winner row (gold color)
- [ ] Percentage shown inside bar when > 8%

### A6. Admin Panel (`/admin-panel/`)
- [ ] Navbar: maroon, brand icon, "Admin Panel" text, role badge
- [ ] **Election List View**: search input, status filter dropdown, type filter dropdown
- [ ] Election rows with badges (status + type)
- [ ] Action buttons (eye + trash icons)
- [ ] Create Campus / Create College buttons
- [ ] **Election Detail View**: back button, election name, status + type badges
- [ ] Primary action button changes by status (Activate/Close/Publish/Published)
- [ ] **Overview Tab**: 4 metric cards, readiness checklist (draft only)
- [ ] **Positions Tab**: position sections with candidate cards showing photos, add candidate + upload photo buttons
- [ ] **Voter Roll Tab**: batch assignment, college breakdown table, unmatched records
- [ ] **Lifecycle Tab**: 4 lifecycle steps with active highlighting, timeline bar

---

## B. Candidate Photo Upload

### B1. Upload Flow
- [ ] Navigate to admin panel → election detail → Positions tab
- [ ] Click camera icon on a candidate
- [ ] Upload modal appears with file input
- [ ] Select a JPEG/PNG/WebP image < 2 MB
- [ ] Preview appears in modal
- [ ] Click Upload → success toast, photo updates in candidate card

### B2. Validation
- [ ] Upload a `.txt` file renamed to `.jpg` → error: "Invalid image file"
- [ ] Upload a file > 2 MB → error: "Photo too large"
- [ ] Upload an empty file (0 bytes) → error: "Photo file is empty"
- [ ] Upload a valid `.png` → succeeds
- [ ] Upload a valid `.webp` → succeeds

### B3. Display
- [ ] Admin panel: candidate card shows circular photo
- [ ] Ballot page: candidate row shows circular photo
- [ ] Results page: candidate result shows circular photo
- [ ] Candidates without photos show person-icon placeholder

---

## C. Registrar Import Batch

### C1. Batch Management
- [ ] Admin panel → click "Registrar Batches" in navbar
- [ ] Click "New Batch" → fill batch_name, academic_year, semester → Create
- [ ] New batch appears in list with "Active" badge and "0 students"

### C2. CSV Import
- [ ] Click "Import" on a batch
- [ ] Upload a valid CSV with columns: student_id, full_name, date_of_birth, college, course, year
- [ ] Success: "Import complete: X created, Y updated, Z skipped"
- [ ] Student count updates in batch card

### C3. CSV Security
- [ ] Upload CSV with cell `=SUM(A1:A10)` as student name → cell should be stored with `'` prefix
- [ ] Upload CSV > 10 MB → error: "File too large"
- [ ] Upload non-UTF8 file → error: "CSV file is invalid or corrupt"
- [ ] Upload CSV with 50,001+ rows → error: "File has too many rows"

### C4. Assign to Election
- [ ] Go to election detail → Voter Roll tab
- [ ] Click "Assign Batch"
- [ ] Select a batch from dropdown → Assign
- [ ] Voter roll generates: verified count + unmatched count displayed
- [ ] College breakdown table populates

---

## D. College Representative Filtering Fix

### D1. Setup
- [ ] Create a campus election with `house_college` positions
- [ ] Ensure candidates are assigned to different colleges
- [ ] Register students from different colleges in voter roll

### D2. Verification
- [ ] Login as a student from College of Engineering
- [ ] Go to ballot → house_college position should ONLY show candidates from College of Engineering
- [ ] Login as a student from College of Arts and Sciences
- [ ] Go to ballot → house_college position should ONLY show candidates from College of Arts and Sciences
- [ ] Executive and Senate positions should show ALL candidates regardless of college

---

## E. Security Checks

### E1. Session
- [ ] After login, session expires after 1 hour of inactivity (check `SESSION_COOKIE_AGE = 3600`)
- [ ] Logout clears session completely

### E2. Photo Upload Path
- [ ] Upload a photo → check `media/candidate_photos/<election_id>/` directory
- [ ] Filename is a UUID hex string + `.jpg` (no original filename preserved)

### E3. Admin Permissions
- [ ] Student user cannot access `/api/admin/elections/setup/*` endpoints (403)
- [ ] Unauthenticated requests to admin endpoints return 403

---

## F. Regression Checks

- [ ] All 424 existing tests pass: `pytest tests/ -x --tb=short -q`
- [ ] Student login/logout works
- [ ] Admin login/logout works
- [ ] Election lifecycle (Draft → Active → Closed → Published) works
- [ ] Ballot submission works
- [ ] Results display correctly
- [ ] Audit log records all actions

---

## Checklist Summary

| Area | Items | Status |
|------|-------|--------|
| Visual Design | 6 pages | ☐ |
| Photo Upload | 3 sections | ☐ |
| Registrar Batch | 4 sections | ☐ |
| College Filtering | 2 sections | ☐ |
| Security | 3 sections | ☐ |
| Regression | 7 items | ☐ |
