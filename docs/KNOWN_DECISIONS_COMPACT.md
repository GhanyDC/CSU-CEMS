# CEMS Known Decisions Compact

Status: Frozen decisions reference  
Purpose: Use this file in Opus prompts instead of resending the full planning documents every time.

---

## 1. Scope
- Version 1 supports **Campus Elections** and **College Elections** only.
- University-wide federation elections are out of scope for version 1.
- The platform is intended for student elections only.

---

## 2. Official colleges
The system must support these exact college names:
- College of Humanities and Social Sciences
- College of Natural Sciences and Mathematics
- College of Public Administration
- College of Information and Computing Sciences
- College of Architecture and Engineering
- College of Industrial Technology
- College of Human Kinetics
- College of Veterinary Medicine
- College of Nursing

These names are authoritative for filtering, election scope, counts, and reporting.

---

## 3. Election schedule rules
- Campus elections and college elections happen on **separate schedules**.
- College elections happen **simultaneously** across colleges.
- College elections must be modeled as **separate election records**, one per college, even when they share the same schedule.
- Recommended operational constraint:
  - only one active campus election at a time
  - only one active college election per college at a time

---

## 4. Official voter roll rule
The official voter roll is:

**registrar import filtered by verification form**

Meaning:
- registrar data is the master identity source
- verification form filters who becomes an approved voter
- the final voter roll must be frozen before voting opens
- only approved voters may submit ballots

Do not use a "vote first, validate later" approach.

---

## 5. Authentication rules
### Student authentication
- Students log in with:
  - student ID
  - birthdate

### Admin authentication
- Admins must not use only student ID + birthdate.
- Admin access must use a separate admin authentication flow.
- Admin login should use:
  - admin username or official email
  - password
- Stronger second-step verification may be added later.

---

## 6. Admin roles
### Electoral Board Head
- Held by the Vice President as head of the electoral board.
- This role alone may:
  - finalize voter rolls
  - start elections
  - close elections
  - publish results
  - approve emergency election actions when needed

### Electoral Board Operators
May:
- create draft elections
- bulk-create college elections
- import registrar data
- import verification-form data
- review matched/unmatched records
- prepare candidates and positions while election is in Draft
- review counts and readiness

May not:
- finalize voter rolls
- start elections
- close elections
- publish results

### Tally Watchers
Read-only monitoring role.

### Auditors / Read-only Oversight
Read-only inspection role.

### Technical Support
System health and infrastructure only. No election-authority actions.

---

## 7. Election lifecycle
The system uses exactly four election states:
- Draft
- Active
- Closed
- Published

Meaning:
- **Draft**: setup stage, not votable
- **Active**: voting open, core configuration locked
- **Closed**: no more ballots accepted, post-close review allowed to authorized roles
- **Published**: final results visible to eligible students

---

## 8. Ballot model decisions
The system must not rely on a single global "has voted" flag.

Required direction:
- one student can cast **one ballot per election**
- one ballot contains **many selections**
- one student may cast:
  - one campus election ballot
  - one college election ballot for their own college

Election-specific voting state is required.

---

## 9. Election templates
### Campus election template
Positions:
- President — choose 1
- Vice President — choose 1
- Senators — choose up to 12
- College Representatives — generate according to the constitution
- Party-list Representatives — generate according to the constitution

### College election template
Positions:
- Governor — choose 1
- Vice Governor — choose 1
- Board Members — choose up to 8

The system should be template-driven so non-technical admins do not have to build ballots from scratch.

---

## 10. Candidate handling
- The system must not automatically decide whether a candidate is qualified.
- Qualification is handled externally during filing/interview review.
- The system only needs to manage ballot participation and status.
- Candidate status should support at least:
  - Active
  - Inactive
- Candidates should not be silently deleted from election history.
- Candidate lists should be editable in Draft and locked once Active.

---

## 11. 50% + 1 rule
The 50% + 1 rule applies to both campus and college positions.

Denominator basis:
- Campus positions: total approved campus voter roll
- College election positions: approved voter roll of that college election
- College Representatives in the campus election: approved voter roll of the represented college

All denominator calculations must use the **final frozen approved voter roll**, not raw registrar counts and not all who attempted to vote.

---

## 12. Visibility rules
### During Active
- Students: no results
- Tally Watchers: turnout and voting-progress visibility only
- Operators: operational monitoring only
- Electoral Board Head: operational monitoring only
- No general live per-candidate tallies during Active voting

### After Close, before Publish
- Authorized roles may review tallies for canvassing
- Results are still not public to students

### After Publish
- Eligible students can view final results

---

## 13. Admin UX rules
- Non-technical admins should never have to input UUIDs manually.
- Election creation must be button-based and template-driven.
- Bulk creation of simultaneous college elections is required.
- Admin setup should include a readiness/review checklist before an election may be started.

---

## 14. Voter-roll dashboard requirements
The system should be able to show:
- total imported students
- total verification-form submissions
- matched approved voters
- approved voters overall
- approved voters per college
- unmatched records
- duplicate records
- turnout overall
- turnout per college

---

## 15. Security and audit rules
At minimum, log:
- student login success/failure
- admin login success/failure
- account lockouts
- voter-roll imports and finalization
- candidate create/edit/status changes
- election create/edit
- start / close / publish actions
- ballot submission
- duplicate ballot attempts
- unauthorized access attempts

Also require:
- session timeout
- CSRF protection
- backend validation of ballot rules
- prevention of cross-college ballot access
- no shared admin accounts

---

## 16. Version 1 exclusions
Out of scope for version 1:
- automatic candidate qualification logic
- dynamic constitutional interpretation by the system
- real-time public live tallies during active voting
- university-wide federation election support
- full independent college-admin authorities
- mobile-first or app-specific redesign

