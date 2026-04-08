# Campus Election Management System (CEMS)
## System Source of Truth

Version: 1.0  
Status: Authoritative planning reference  
Purpose: This document is the single source of truth for planning, implementing, reviewing, and testing the CEMS election platform.

---

## 1. Project overview

CEMS is an election platform intended for student elections at the campus and college levels.

This version of the system is designed for:
- Campus elections
- College elections

This version is **not** intended to support university-wide federation elections, national elections, or public elections.

The system must prioritize:
- election integrity
- correct voter eligibility
- one-ballot-per-election enforcement
- auditability
- clear admin control
- low operational confusion for non-technical users

---

## 2. Final scope for version 1

### In scope
- Separate campus and college election support
- Role-based admin access
- Separate admin authentication from student authentication
- Registrar-based voter import
- Verification-form-based voter filtering
- Finalized voter roll per election
- Campus election creation from template
- Bulk creation of simultaneous college elections
- Election lifecycle: Draft -> Active -> Closed -> Published
- Student dashboard showing only eligible elections
- One ballot per student per election
- Multi-position ballots
- Final result publication to eligible students
- Audit logging for sensitive actions
- Deployment planning for approximately 10,000 students and 9 colleges

### Out of scope for version 1
- Automatic candidate qualification decision-making
- Complex legal adjudication logic
- Dynamic constitutional interpretation by the system
- Real-time public live results during active voting
- Full multi-tenant independent college admin authorities
- University-wide federation election support
- Mobile app-specific flows
- External identity providers or SSO

---

## 3. Official colleges

The system must support the following 9 colleges:

1. College of Humanities and Social Sciences
2. College of Natural Sciences and Mathematics
3. College of Public Administration
4. College of Information and Computing Sciences
5. College of Architecture and Engineering
6. College of Industrial Technology
7. College of Human Kinetics
8. College of Veterinary Medicine
9. College of Nursing

These names must be treated as the official college values used for voter filtering, college election scoping, dashboard counts, and reporting.

---

## 4. Election types and schedules

### Election types
The system supports exactly two election types:
- Campus Election
- College Election

### Schedule rules
- Campus elections and college elections happen on **separate schedules**.
- College elections happen **simultaneously** across colleges.
- The system should model college elections as **separate election records**, one per college, even when they share the same start and end schedule.

### Recommended operational rule
- Only one active campus election at a time
- Only one active college election per college at a time

---

## 5. Official voter roll rule

The official voter roll is defined as:

**official voter roll = registrar import filtered by verification form**

This means:
- the registrar dataset is the master identity source
- the verification form filters and confirms who is included in the official voter roll
- the final voter roll must be frozen before the election starts
- only students on the finalized voter roll may submit a ballot

### Important implications
- Students may log in and check status, but ballot access is only for approved voters.
- Ballots must not be accepted first and validated later.
- Election denominators must come from the finalized voter roll, not from raw registrar counts and not from all who attempted to vote.

---

## 6. Authentication rules

### Student authentication
Students authenticate using:
- student ID
- birthdate

This applies only to the voter-facing side of the system.

### Admin authentication
Admin roles must **not** use only student ID + birthdate.

Admins must use a separate admin authentication flow with:
- admin username or official email
- password
- optional stronger second-step verification in future

### Security decision
Admin authority, especially the Electoral Board Head role, must not rely on credentials that are easily guessable by other students.

---

## 7. Admin roles and responsibilities

The system uses role-based admin access.

### 7.1 Electoral Board Head
This role is held by the Vice President, who serves as the head of the electoral board.

This role alone may:
- finalize voter rolls
- start elections
- close elections
- publish results
- approve emergency election actions when needed

### 7.2 Electoral Board Operators
These are central-board support accounts.

They may:
- create draft elections
- bulk-create college elections
- import registrar data
- import verification-form data
- review matched and unmatched records
- prepare candidates and positions while elections are still in Draft
- review counts and operational readiness

They may not:
- finalize voter rolls
- start elections
- close elections
- publish results

### 7.3 Tally Watchers
This is a read-only monitoring role.

They may view:
- turnout progress
- number of students who have voted
- status of active elections
- post-close tallies if allowed by role settings

They may not edit elections, candidates, voter rolls, or publication state.

### 7.4 Auditors / Read-only Oversight
They may view:
- election setup
- logs
- counts
- post-close tallies
- published results

They may not modify election data.

### 7.5 Technical Support
They may access:
- system health
- infrastructure and error monitoring

They may not:
- alter candidates
- alter tallies
- start, close, or publish elections
- modify official voter rolls

---

## 8. Election lifecycle

The system uses a strict 4-state election lifecycle.

### Draft
Meaning:
- setup stage
- positions, candidates, and settings may still be reviewed
- students cannot vote

### Active
Meaning:
- voting is open
- students may submit ballots if eligible
- core election configuration is locked

### Closed
Meaning:
- voting is finished
- no more ballots are accepted
- tallies may be reviewed by authorized roles
- results are not yet public to students

### Published
Meaning:
- results are visible to eligible students
- the election becomes read-only from a user workflow perspective

### Role restriction
Only the Electoral Board Head may transition the election to:
- Active
- Closed
- Published

---

## 9. Election templates

The admin workflow must be template-driven.

### 9.1 Campus election template
The system should auto-generate the campus ballot positions based on the constitution.

Configured positions:
- President -> choose 1
- Vice President -> choose 1
- Senators -> choose up to 12
- College Representatives -> generated from the constitutional rule
- Party-list Representatives -> generated from the constitutional rule

### 9.2 College election template
The system should auto-generate the college ballot positions.

Configured positions:
- Governor -> choose 1
- Vice Governor -> choose 1
- Board Members -> choose up to 8

### Template rule
Admins should not need to manually rebuild the full ballot structure each time.
The template should generate the standard positions automatically, with limited draft-only adjustments if necessary.

---

## 10. Candidate management rules

The system does **not** determine whether a candidate is qualified.
Candidate qualification is handled outside the system through filing and interview procedures.

### Inside the system, candidate handling is limited to:
- assigning a candidate to the correct election and position
- setting the candidate status
- showing or hiding the candidate from the ballot

### Candidate statuses
Minimum statuses:
- Active
- Inactive

### Operational rule
- Active candidates appear on the ballot
- Inactive candidates do not appear on the ballot
- Candidates must not be silently deleted from election history
- Candidate edits are allowed only while the election is in Draft
- Once the election becomes Active, candidate list changes should be locked except for controlled emergency procedures

---

## 11. Position and ballot rules

The system must not rely on a single global has-voted flag.

### Correct voting model
- one student may cast one ballot per election
- a ballot contains many selections across positions
- voting status is election-specific, not global

### Student election participation
A student may:
- vote in one campus election when eligible
- vote in one college election for their own college when eligible

### Ballot validation
For each ballot submission, the system must validate:
- student is authenticated
- student is in the finalized voter roll for that election
- election is Active
- student has not already submitted a ballot for that election
- selections are valid for each position
- selection count does not exceed the allowed maximum for the position

---

## 12. Student election visibility rules

After login, the system checks:
- finalized voter-roll eligibility
- election schedule and status
- student college
- election scope

### Student dashboard behavior
If eligible, the student should see only the elections they are allowed to vote in.

Examples:
- An eligible student should see the active campus election during the campus schedule.
- An eligible student should see only their own college election during the college election schedule.
- A CICS student should not see CHSS, Nursing, or other college ballots.

If not eligible, the student should not see a ballot. The system should show a clear status message instead.

---

## 13. 50% + 1 rules

The 50% + 1 rule applies to both campus and college positions.

### Denominator rules
For campus-wide positions:
- use the total finalized approved voter roll for the campus election

For college election positions:
- use the finalized approved voter roll for that specific college election

For College Representatives in the campus election:
- use the finalized approved voter roll of the represented college

### Important rule
All 50% + 1 calculations must be based on the frozen approved voter roll, not on all imported students and not on all who attempted to vote.

---

## 14. Visibility and tally rules

### During Active voting
Best-practice rule:
- do not show live per-candidate vote totals to students
- do not show live per-candidate vote totals to general admin roles

Allowed visibility during Active:
- turnout overall
- turnout by college
- number of students who have voted
- operational status of elections

### During Closed, before Published
Authorized roles may review tallies for canvassing and validation.

### During Published
Eligible students may view final results.

### Decision for version 1
The system should favor fairness and reduced influence over live race monitoring. Therefore, candidate tallies should remain hidden until the election is Closed.

---

## 15. Required dashboards and counts

### Before election starts
The admin side should show:
- total registrar imports
- total verification-form submissions
- total matched approved voters
- unmatched submissions
- duplicate submissions
- approved voters overall
- approved voters per college

### During active election
The admin side should show:
- turnout overall
- turnout per college
- total ballots submitted
- election status

### After close
The admin side should show:
- tallies per position
- turnout percentage
- threshold calculations for lone-candidate positions
- basis counts used in those calculations

### After publish
Students should see:
- final results
- vote totals by position
- turnout summary if approved for display

---

## 16. Admin UX requirements

The admin side must be understandable to non-technical users.

### Required design principles
- no manual UUID entry for normal workflows
- plain-language labels
- template-based setup
- checklist-based readiness review
- button-based state transitions

### Core admin workflow
1. Import registrar data
2. Import verification-form data
3. Review and match records
4. Finalize voter roll
5. Create election from template
6. Add candidates
7. Review readiness checklist
8. Save as Draft
9. Start election
10. Close election
11. Publish results

---

## 17. Audit logging requirements

The system must log at minimum:
- student login success/failure
- admin login success/failure
- account lockouts
- registrar imports
- verification-form imports
- voter-roll finalization
- candidate create/edit/status changes
- election create/edit actions
- election start
- election close
- result publication
- ballot submission
- duplicate ballot attempts
- unauthorized access attempts
- suspicious activity

Audit history must support review and dispute resolution.

---

## 18. Security rules

### Required security controls
- separate admin authentication
- session protection
- CSRF protection on state-changing requests
- lockouts and rate limits where applicable
- server-side validation for all ballot submissions
- strict authorization checks on every sensitive action
- prevention of cross-college ballot access
- prevention of double submission
- no shared admin accounts

### Core principle
Security decisions must prefer integrity and correctness over convenience.

---

## 19. Deployment assumptions

The system is expected to support approximately:
- 10,000 students
- 9 colleges
- 1 to 2 day election windows

### Deployment expectations
- PostgreSQL in production
- staging environment before release
- load testing before election day
- backup before election opens
- restore rehearsal before live deployment
- operational monitoring during the election window
- change freeze before active election begins

---

## 20. Testing expectations

Testing must include:
- voter-roll import and matching tests
- role-permission tests
- wrong-college access tests
- duplicate ballot prevention tests
- ballot validation tests
- lone-candidate threshold tests
- results visibility tests
- state-transition tests
- PostgreSQL concurrency tests
- dry-run mock election before live deployment

---

## 21. Implementation principles for coding agents

Any implementation agent or model must follow these rules:
- do not change frozen policy decisions without explicit approval
- do not simplify the election model back to a single global voting flag
- do not expose UUIDs in normal admin workflows
- do not add automatic candidate-qualification logic
- do not show live candidate tallies during Active voting unless explicitly approved later
- preserve auditability
- prefer explicit, conservative behavior over clever shortcuts

---

## 22. Frozen decisions summary

The following decisions are frozen unless explicitly revised:
- scope is campus and college elections only
- official voter roll = registrar import filtered by verification form
- campus and college elections are on separate schedules
- college elections happen simultaneously
- the Vice President as Electoral Board Head alone may start, close, and publish
- role-based admin access is required
- admin authentication is separate from student authentication
- the system does not determine candidate qualification
- 50% + 1 applies to both campus and college positions
- active/inactive status is used for candidate visibility and withdrawal handling in version 1
- results are only visible to eligible students after publish
- separate college election records are preferred over one giant combined college election

---

## 23. Version control rule for this document

This document is the primary planning authority for implementation work.
If implementation details, prompts, or earlier notes conflict with this document, this document should take precedence unless a newer approved revision explicitly replaces it.

