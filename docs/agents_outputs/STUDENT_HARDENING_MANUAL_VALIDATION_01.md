# STUDENT HARDENING MANUAL VALIDATION CHECKLIST 01

**Date:** 2026-04-10  
**Scope:** Student-side pages only (login, dashboard, ballot, results)

---

## Pre-Conditions

- [ ] Server running (`python manage.py runserver`)
- [ ] At least one Active election exists with ≥2 positions  
- [ ] At least one Published election exists  
- [ ] Test student accounts exist on voter rolls (different colleges)  
- [ ] Campus election with HOUSE_COLLEGE positions and candidates from multiple colleges  

---

## 1. Login Checks

| # | Step | Expected Outcome | Pass |
|---|------|-------------------|------|
| 1.1 | Navigate to `/` | Login page renders, fields visible | ☐ |
| 1.2 | Submit empty form | Validation error shown (not a crash) | ☐ |
| 1.3 | Submit invalid student ID | "Invalid credentials" error | ☐ |
| 1.4 | Submit valid student ID + wrong DOB | "Invalid credentials" error | ☐ |
| 1.5 | Submit valid student ID + correct DOB | Redirect to `/dashboard/` | ☐ |
| 1.6 | Try SQL injection in student ID field | Rejected, no error trace | ☐ |
| 1.7 | Login with student not on any voter roll | Dashboard shows "No eligible elections" | ☐ |

---

## 2. Dashboard Checks

| # | Step | Expected Outcome | Pass |
|---|------|-------------------|------|
| 2.1 | View dashboard after login | Dashboard renders with status cards | ☐ |
| 2.2 | Active election visible | "Vote Now" button shown | ☐ |
| 2.3 | Published election visible | "View Results" button shown | ☐ |
| 2.4 | Draft election NOT visible | Not listed at all | ☐ |
| 2.5 | Closed (unpublished) election NOT visible | Not listed at all | ☐ |
| 2.6 | College election for OTHER college | Not visible to student | ☐ |
| 2.7 | Logout button works | Returns to login page, session cleared | ☐ |
| 2.8 | Refresh after logout | Returns to login, no dashboard data | ☐ |

---

## 3. Ballot Selection Checks (Single-Select Position)

| # | Step | Expected Outcome | Pass |
|---|------|-------------------|------|
| 3.1 | Click candidate card | Card gets green border, counter shows 1/1 | ☐ |
| 3.2 | Click different candidate | Previous deselected, new selected | ☐ |
| 3.3 | Click selected candidate again | Card deselected, counter back to 0/1 | ☐ |
| 3.4 | Click Abstain card | Abstain card selected (yellow border), counter shows "Abstain" | ☐ |
| 3.5 | Click candidate while abstained | Abstain cleared, candidate selected | ☐ |
| 3.6 | Click Abstain while candidate selected | Candidate cleared, abstain selected | ☐ |

---

## 4. Ballot Selection Checks (Multi-Select Position)

| # | Step | Expected Outcome | Pass |
|---|------|-------------------|------|
| 4.1 | Click first candidate | Selected, counter 1/N | ☐ |
| 4.2 | Click second candidate | Both selected, counter 2/N | ☐ |
| 4.3 | Click candidates up to max | All selected, counter N/N | ☐ |
| 4.4 | Click one more beyond max | Toast warning, selection blocked | ☐ |
| 4.5 | Deselect one, then select another | Works normally, counter correct | ☐ |
| 4.6 | Click Abstain with candidates selected | All candidates cleared, abstain active | ☐ |
| 4.7 | Click candidate while abstained | Abstain cleared, candidate selected | ☐ |

---

## 5. Abstain Card Checks

| # | Step | Expected Outcome | Pass |
|---|------|-------------------|------|
| 5.1 | Abstain card is in same grid as candidates | Card visible within position candidate grid | ☐ |
| 5.2 | Abstain card has dashed border | Distinct from solid candidate card borders | ☐ |
| 5.3 | Selected abstain card shows yellow/gold | Not green (green = candidate) | ☐ |
| 5.4 | Abstain card has dash-circle icon | Not a checkbox or radio button | ☐ |
| 5.5 | Keyboard: Tab to abstain card, press Enter | Toggles abstain selection | ☐ |
| 5.6 | Keyboard: Tab to abstain card, press Space | Toggles abstain selection | ☐ |

---

## 6. Review/Submit Sync Checks (THE CRITICAL BUG FIX)

| # | Step | Expected Outcome | Pass |
|---|------|-------------------|------|
| 6.1 | Select candidate in position 1 | Review section updates immediately | ☐ |
| 6.2 | Change selection in position 1 | Review section reflects new choice | ☐ |
| 6.3 | Select abstain in position 2 | Review shows "⊘ Abstain" for position 2 | ☐ |
| 6.4 | Remove all selections | Review shows "⚠ No selection" for all | ☐ |
| 6.5 | Mix selections: some candidates, some abstain, some empty | Review reflects exact state per position | ☐ |
| 6.6 | Rapidly toggle selections across positions | Review stays perfectly in sync, no stale data | ☐ |
| 6.7 | Submit button state matches: ≥1 selection → enabled | Button enables only when appropriate | ☐ |
| 6.8 | All abstain → submit still enabled | Can abstain on everything (blocked on submit with message) | ☐ |
| 6.9 | Click submit with zero actual candidates | Toast: "must vote for at least one candidate" | ☐ |

---

## 7. Duplicate Submission Checks

| # | Step | Expected Outcome | Pass |
|---|------|-------------------|------|
| 7.1 | Submit valid ballot | Success modal appears | ☐ |
| 7.2 | Close modal, navigate back to ballot for same election | Prevented (already voted indicator) | ☐ |
| 7.3 | Use browser back button after submit | No re-submission possible | ☐ |
| 7.4 | Double-click submit button rapidly | Only one request sent (button disabled immediately) | ☐ |
| 7.5 | Open ballot in two tabs, submit from both | First succeeds, second gets 409 with friendly message | ☐ |

---

## 8. Mobile / Responsive Checks

| # | Step | Expected Outcome | Pass |
|---|------|-------------------|------|
| 8.1 | View dashboard on 375px width | All elements visible, no horizontal scroll | ☐ |
| 8.2 | View ballot on 375px width | Candidate cards stack properly | ☐ |
| 8.3 | Review section on 375px | Position rows stack (label above, value below) | ☐ |
| 8.4 | Submit button on mobile | Full width, easy to tap | ☐ |
| 8.5 | Results page on 375px width | Results bars readable, no overflow | ☐ |
| 8.6 | Success modal on mobile | Fully visible, no clipping | ☐ |
| 8.7 | Touch: tap candidate card | Selection registers on first tap | ☐ |
| 8.8 | Touch: tap abstain card | Abstain registers on first tap | ☐ |
| 8.9 | Tablet (768px) | Intermediate layout, 2-column cards | ☐ |

---

## 9. College Representative Filtering Checks

| # | Step | Expected Outcome | Pass |
|---|------|-------------------|------|
| 9.1 | Login as CAS student, open campus election ballot | HOUSE_COLLEGE position shows only CAS candidates | ☐ |
| 9.2 | Login as COE student, open same election | HOUSE_COLLEGE shows only COE candidates | ☐ |
| 9.3 | EXECUTIVE position on same ballot | Shows ALL candidates regardless of college | ☐ |
| 9.4 | HOUSE_COLLEGE with no candidates for student's college | Position not shown at all on ballot | ☐ |
| 9.5 | College election ballot | All positions show, no cross-college filtering | ☐ |

---

## 10. Confirmation Checks

| # | Step | Expected Outcome | Pass |
|---|------|-------------------|------|
| 10.1 | After successful submit | Modal appears with green checkmark | ☐ |
| 10.2 | Modal shows election name | Correct election name displayed | ☐ |
| 10.3 | Modal shows timestamp | Time is reasonable (current time) | ☐ |
| 10.4 | Modal shows ballot ID | Non-empty, looks like a hash | ☐ |
| 10.5 | Click outside modal | Modal does NOT dismiss (static backdrop) | ☐ |
| 10.6 | Press Escape on modal | Modal does NOT close | ☐ |
| 10.7 | Click "Back to Dashboard" | Returns to dashboard, election shows "Submitted" | ☐ |
| 10.8 | Modal does NOT show individual vote details | Privacy on shared devices | ☐ |

---

## 11. Results Checks

| # | Step | Expected Outcome | Pass |
|---|------|-------------------|------|
| 11.1 | Navigate to results for Published election | Results page renders | ☐ |
| 11.2 | Election summary shows total ballots | Number is reasonable | ☐ |
| 11.3 | Per-position results show candidate bars | Bars proportional to votes | ☐ |
| 11.4 | Winner has "Winner" badge | Green badge on top candidate | ☐ |
| 11.5 | Candidate photo loads | Photo visible, or falls back to placeholder | ☐ |
| 11.6 | Photo fails to load | Placeholder image shown (no broken image icon) | ☐ |
| 11.7 | Try results for non-Published election | 403 or redirect, not crash | ☐ |
| 11.8 | Try results for election student isn't on roll for | 403 "not eligible" | ☐ |

---

## 12. Session / Security Checks

| # | Step | Expected Outcome | Pass |
|---|------|-------------------|------|
| 12.1 | Wait for session to expire (or clear cookies) | Next action shows session expired banner | ☐ |
| 12.2 | Session expired → auto redirect | Redirected to login after delay | ☐ |
| 12.3 | Direct URL access to `/dashboard/` without login | Redirect to login | ☐ |
| 12.4 | Direct URL access to `/ballot/` without login | Redirect to login | ☐ |
| 12.5 | Direct URL access to `/results/` without login | Redirect to login | ☐ |

---

## Expected Test Results

| Test File | Expected | Notes |
|-----------|----------|-------|
| `tests/test_student_hardening.py` | 41 pass, 0 fail | New hardening tests |
| `tests/` (full suite) | 539 pass, 0 fail | No regressions |
