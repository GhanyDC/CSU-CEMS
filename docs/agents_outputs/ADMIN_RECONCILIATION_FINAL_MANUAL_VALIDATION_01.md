# Admin Reconciliation — Final Manual Validation Checklist

**Date**: 2026-04-10

---

## Pre-Validation

1. Start dev server: `$env:DJANGO_SETTINGS_MODULE = "config.settings.local"; python manage.py runserver`
2. Log in as EB Head, Operator, and Tally Watcher (use pilot data accounts or create via Django admin)
3. Have elections in Draft, Active, Closed, and Published states

---

## A. Admin Tab Structure

| # | Test | Expected | Pass? |
|---|------|----------|-------|
| A1 | Open any election detail | Exactly 4 tabs: Overview, Positions & Candidates, Voter Roll, Lifecycle | |
| A2 | Confirm no Monitoring tab | No tab labeled "Monitoring" exists | |
| A3 | Confirm no Readiness tab | No tab labeled "Readiness" exists | |

---

## B. Admin Roles

| # | Test | Steps | Expected | Pass? |
|---|------|-------|----------|-------|
| B1 | EB Head full access | Login → Navigate all tabs and actions | All visible and functional | |
| B2 | Operator setup access | Login → Create election, add candidates | Works | |
| B3 | Operator position blocked | Login → Try to add/edit position | No position management buttons visible | |
| B4 | Tally Watcher read-only | Login → Browse elections | List and detail visible, no create/edit buttons | |
| B5 | Auditor denied | Login → Try any admin endpoint | 403 on all endpoints | |

---

## C. Overview Tab

| # | Test | Steps | Expected | Pass? |
|---|------|-------|----------|-------|
| C1 | Draft Overview | Open Draft election → Overview | Status badge, schedule, candidate count, eligible voters, readiness checklist | |
| C2 | Active Overview | Open Active election → Overview | Votes cast, turnout %, time remaining, voter roll summary | |
| C3 | Closed Overview | Open Closed election → Overview | Final turnout, vote count, voting period | |
| C4 | Readiness checklist (Draft) | Open Draft → Overview | Pre-flight checklist with steps and blocking issues | |
| C5 | No readiness (Active) | Open Active → Overview | No readiness section | |
| C6 | Export buttons (Active) | Open Active → Overview | Turnout CSV + Turnout Text visible; no Tally/Participation/Audit | |
| C7 | Export buttons (Closed, EB Head) | Open Closed → Overview as EB Head | All 5 export buttons visible | |
| C8 | Export buttons (Closed, Operator) | Open Closed → Overview as Operator | Only Turnout CSV + Text visible | |
| C9 | Export buttons (Closed, TW) | Open Closed → Overview as TW | Turnout CSV + Text + Tally CSV visible; no Participation/Audit | |
| C10 | No exports (Draft) | Open Draft → Overview | No Exports card | |

---

## D. Positions & Candidates Tab — Draft

| # | Test | Steps | Expected | Pass? |
|---|------|-------|----------|-------|
| D1 | EB Head position CRUD | Add, edit, delete position | All work | |
| D2 | EB Head drag reorder | Drag position up/down | Reorder saves, position order changes | |
| D3 | Operator no reorder | Login as Operator → Positions tab | No grip handle, no drag | |
| D4 | Operator no position buttons | Login as Operator | No Add Position, Edit, Delete position buttons | |
| D5 | Operator can add candidate | Login as Operator → + Add Candidate | Modal opens, candidate saved | |
| D6 | TW read-only | Login as TW → Positions tab | Static roster, no action buttons | |
| D7 | Add Candidate modal (pre-selected) | Click "+ Add Candidate" on a position | Position shown as read-only pill, not dropdown | |
| D8 | Add Candidate College optional | Open modal | College field labeled "(optional)" | |

---

## E. Positions & Candidates Tab — Active (Live Monitoring)

| # | Test | Steps | Expected | Pass? |
|---|------|-------|----------|-------|
| E1 | State indicator | Open Active election → Positions tab | "Active — Live Monitoring" banner visible | |
| E2 | Participation bar per position | Each position block | Shows "Participation: X / Y (Z%)" and "Abstained: N" | |
| E3 | EB Head sees per-candidate votes | Login as EB Head → Active → Positions | Each candidate row shows vote count and percentage | |
| E4 | Operator sees no candidate votes | Login as Operator → same election | No per-candidate vote counts visible | |
| E5 | Operator sees "Participation summary only" badge | Login as Operator → Positions | Badge shown next to state indicator | |
| E6 | TW sees no candidate votes | Login as TW → same election | No per-candidate vote counts; participation data shown | |
| E7 | No edit buttons | All roles → Active → Positions | No Add/Edit/Delete/Reorder controls | |

---

## F. Positions & Candidates Tab — Closed/Published (Review Mode)

| # | Test | Steps | Expected | Pass? |
|---|------|-------|----------|-------|
| F1 | State indicator | Closed election → Positions | "Closed — Review Mode" banner | |
| F2 | EB Head full tally | Login as EB Head | Per-candidate vote counts and percentages visible | |
| F3 | TW full tally | Login as TW | Per-candidate vote counts and percentages visible | |
| F4 | Operator redacted | Login as Operator | Participation data only; no per-candidate votes | |
| F5 | Published state | Published election → Positions | "Published — Final Results" banner | |

---

## G. Tally Endpoint Verification

| # | Test | Steps | Expected | Pass? |
|---|------|-------|----------|-------|
| G1 | EB Head tally during Active | GET /tally/ as EB Head | 200, full per-candidate data, no `redacted` flag | |
| G2 | Operator tally during Active | GET /tally/ as Operator | 200, `redacted: true`, no `votes` fields | |
| G3 | TW tally during Active | GET /tally/ as TW | 200, `redacted: true`, no `votes` fields | |
| G4 | Operator tally during Closed | GET /tally/ as Operator | 200, `redacted: true`, no `votes` fields | |
| G5 | TW tally during Closed | GET /tally/ as TW | 200, full data, `votes` present | |
| G6 | All roles during Draft | GET /tally/ | 403 for all roles | |

---

## H. Voter Roll Tab

| # | Test | Steps | Expected | Pass? |
|---|------|-------|----------|-------|
| H1 | Pipeline visible (Draft, not finalized) | Open Draft | 4-step pipeline: Link Batch → Import → Generate → Finalize | |
| H2 | Metrics row | Any state with data | Total Imported, Matched, Unmatched, Approved with percentages | |
| H3 | College breakdown | After voter roll generated | Table with college names, approved count, share bar, status | |
| H4 | Finalized banner | Finalized election | Green banner showing who finalized and when | |
| H5 | EB Head finalize button | As EB Head, voter roll generated | "Finalize Now" button in step 4 | |
| H6 | Operator can't finalize | As Operator | No Finalize button | |

---

## I. Lifecycle Tab

| # | Test | Steps | Expected | Pass? |
|---|------|-------|----------|-------|
| I1 | EB Head sees Start | Draft election as EB Head | Start Election button visible (if readiness passes) | |
| I2 | EB Head sees Close | Active election | Close Election button | |
| I3 | EB Head sees Publish | Closed election | Publish Results button | |
| I4 | Operator no lifecycle buttons | Any state as Operator | No lifecycle transition buttons | |
| I5 | TW no lifecycle buttons | Any state as TW | No lifecycle transition buttons | |

---

## J. Export Downloads

| # | Test | Steps | Expected | Pass? |
|---|------|-------|----------|-------|
| J1 | Turnout CSV download | Click Turnout CSV (Active) | CSV file downloads with turnout data | |
| J2 | Turnout Text clipboard | Click Turnout Text | Toast: "Copied to clipboard" | |
| J3 | Tally CSV (EB Head, Closed) | Click Tally CSV | CSV with per-candidate votes and abstain | |
| J4 | Participation CSV (EB Head, Closed) | Click Participation CSV | CSV with student IDs and voted status | |
| J5 | Ballot Audit CSV (EB Head, Closed) | Click Ballot Audit CSV | CSV with truncated hashes, no real student IDs | |
| J6 | Audit log created | Download any export → Check audit log | `EXPORT_GENERATED` event logged | |

---

## K. College Representative Filtering

| # | Test | Steps | Expected | Pass? |
|---|------|-------|----------|-------|
| K1 | Student sees own college reps only | Login as COE student → Vote in campus election | Only COE college rep candidates shown | |
| K2 | Other college reps hidden | Same ballot | No CEBA/CAS/etc. college rep candidates | |

---

## L. Abstain Feature

| # | Test | Steps | Expected | Pass? |
|---|------|-------|----------|-------|
| L1 | Abstain checkbox | Student ballot page | Each position has abstain checkbox | |
| L2 | Abstain deselects candidates | Select then abstain | Candidates deselected | |
| L3 | Candidate deselects abstain | Abstain then select candidate | Abstain unchecked | |
| L4 | All-positions-abstain blocked | Check abstain for ALL positions | Submit blocked: "must vote for at least one candidate" | |
| L5 | Results show abstain | Published results page | Abstain count shown per position | |
| L6 | Admin tally shows abstain | Admin Positions tab (non-draft) | Abstain count shown per position | |

---

## Post-Validation

- Automated tests: **498 passing**, 0 failures, 79% coverage
- Manual validation covers UI interactions and visual confirmations not testable via API
