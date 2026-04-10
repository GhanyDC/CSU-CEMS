# Manual Validation Checklist — Final Admin Panel Run

**Date**: 2026-04-10

---

## Pre-Validation Setup

1. Start the dev server: `python manage.py runserver`
2. Create admin users for each role via Django admin or management command
3. Create a test election in Draft state

---

## A. Admin Roles

| # | Test | Steps | Expected | Pass? |
|---|------|-------|----------|-------|
| A1 | EB Head full access | Login as EB Head → Navigate all tabs | All tabs visible and functional | |
| A2 | Operator can create | Login as Operator → Create new election | Election created | |
| A3 | Operator cannot lifecycle | Login as Operator → Go to Lifecycle tab | No Start/Close/Publish buttons | |
| A4 | Tally Watcher read-only | Login as TW → Browse elections | Can view list and details, no edit buttons | |
| A5 | AUDITOR denied | Login as AUDITOR role user | Redirected or 403 on all admin endpoints | |

## B. Tally Visibility

| # | Test | Steps | Expected | Pass? |
|---|------|-------|----------|-------|
| B1 | EB Head tally during Active | Start an election → View tally endpoint | 200 with full per-candidate data | |
| B2 | TW blocked during Active | Login as TW → Request tally of Active election | 403 Forbidden | |
| B3 | Operator redacted during Active | Login as Operator → Request tally during Active | 200 with summary only, no per-candidate votes | |
| B4 | TW sees tally after Closed | Close election → Login as TW → Request tally | 200 with full data | |

## C. Export System

| # | Test | Steps | Expected | Pass? |
|---|------|-------|----------|-------|
| C1 | Turnout CSV download | Overview tab → Click "Turnout CSV" (Active election) | CSV file downloads with turnout data | |
| C2 | Turnout Text clipboard | Overview tab → Click "Turnout Text" | Toast: "Copied to clipboard", clipboard has text | |
| C3 | Tally CSV after Close | Close election → Click "Tally CSV" | CSV with per-candidate votes and abstain counts | |
| C4 | Participation CSV EB Head only | Login as TW → No Participation CSV button shown | Button hidden for non-EB-Head | |
| C5 | Ballot Audit CSV | Login as EB Head → Click "Ballot Audit CSV" | CSV with truncated hashed IDs, no real student IDs | |
| C6 | Export blocked for Draft | Draft election → Overview tab | No Exports section shown | |
| C7 | Export buttons state-aware | Active election → Check export cards | Tally/Participation CSVs not shown, info message visible | |

## D. Abstain Feature

| # | Test | Steps | Expected | Pass? |
|---|------|-------|----------|-------|
| D1 | Abstain checkbox visible | Go to ballot page | Each position has "Abstain from this position" checkbox | |
| D2 | Abstain deselects candidates | Select a candidate → Check abstain | Candidate deselected, counter shows "Abstain" | |
| D3 | Candidate deselects abstain | Check abstain → Select a candidate | Abstain unchecked, counter updated | |
| D4 | Summary shows abstain | Check abstain for one position, select for another | Summary shows "Abstain" badge for first, candidate for second | |
| D5 | Full abstain blocked | Check abstain for ALL positions (no candidates selected) | Submit → Toast "must vote for at least one candidate" | |
| D6 | Results show abstain count | Publish results → View results page | Abstain count shown per position | |

## E. Position Reorder

| # | Test | Steps | Expected | Pass? |
|---|------|-------|----------|-------|
| E1 | Reorder available in Draft | Open Draft election → Positions tab | Up/down arrows on each position | |
| E2 | Move position up | Click up arrow on second position | Position moves up, page refreshes | |
| E3 | Move position down | Click down arrow on first position | Position moves down | |
| E4 | First position no up | First position | Up arrow disabled | |
| E5 | Last position no down | Last position | Down arrow disabled | |
| E6 | Reorder hidden non-Draft | View Active election → Positions tab | No reorder arrows | |
| E7 | Reorder hidden for Operator | Login as Operator → Draft election → Positions tab | No reorder arrows (position management is EB Head only) | |

## F. Audit Logging

| # | Test | Steps | Expected | Pass? |
|---|------|-------|----------|-------|
| F1 | Export audit logged | Download any export → Check Django admin AuditLog | New `export_generated` event with export type and admin info | |

## G. Voter Roll

| # | Test | Steps | Expected | Pass? |
|---|------|-------|----------|-------|
| G1 | Pipeline steps | Open Draft election → Voter Roll tab | 4-step pipeline shown | |
| G2 | College breakdown | Generate voter roll → View breakdown | Table with college names, counts, share bars | |
| G3 | Metrics accurate | Compare metrics row with college table total | Numbers match | |

## H. Student Ballot Photos

| # | Test | Steps | Expected | Pass? |
|---|------|-------|----------|-------|
| H1 | Photos display | Upload photo for candidate → Vote on ballot page | Photo shown in candidate card | |
| H2 | Placeholder shown | Candidate without photo | Grey person icon placeholder | |

---

## Post-Validation

- Total automated tests: **462 passing**
- Manual validation covers UI interactions not easily testable via API
