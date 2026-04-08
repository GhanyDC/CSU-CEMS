# Bundle 04 — Student Voting, Results, and Monitoring

Status: End-to-end election-flow bundle  
Recommended model use: **Usually Agent mode after Bundles 01–03 are stable**

---

## 1. Purpose
This bundle delivers the student election experience, ballot submission flow, results visibility controls, and monitoring views for authorized roles.

---

## 2. Why this bundle exists
Once admin identity, election models, voter rolls, and setup flows are stable, the system must support:
- student election visibility
- ballot rendering
- review and submit
- turnout monitoring
- post-close tally review
- published results visibility

---

## 3. Scope of this bundle
### In scope
- student dashboard election visibility
- college filtering by student college
- ballot rendering by election and position
- review and submit flow
- atomic ballot submission
- duplicate-prevention checks
- turnout monitoring
- closed-state tally visibility to authorized roles
- published results page for eligible students
- 50% + 1 display and threshold reporting

### Out of scope
- mobile-app-specific redesign
- live public tallies during Active
- heavy deployment/load-testing work

---

## 4. Frozen rules for this bundle
- Students may log in using student ID + birthdate.
- Students may submit ballots only if they are approved voters for that election.
- One student may cast:
  - one campus election ballot
  - one college election ballot for their own college
- Students must not see another college's election.
- Campus and college election schedules are separate.
- No general live per-candidate tallies during Active voting.
- During Active, authorized roles may monitor turnout/progress only.
- After Close, authorized roles may review tallies.
- After Publish, eligible students may view final results.
- 50% + 1 basis:
  - campus positions use approved campus voter roll
  - college positions use approved voters of that college election
  - college representatives in the campus election use approved voters of the represented college

---

## 5. Recommended implementation direction
### Student dashboard
After login, evaluate:
- whether the student is on the finalized voter roll for the relevant election
- whether there is an active campus election
- whether there is an active college election for the student's own college

Show only allowed elections.

### Ballot flow
Recommended steps:
1. open ballot
2. display positions and candidates with selection limits
3. allow review
4. submit ballot
5. backend re-validates everything before acceptance

### Results and monitoring visibility
Recommended behavior:
- Active: turnout only for authorized roles
- Closed: tally review for authorized roles
- Published: final results for eligible students

---

## 6. Deliverables
Expected outputs:
- student dashboard election cards or equivalent
- ballot rendering with position-based rules
- review/confirmation step
- atomic ballot submission service/use-case
- turnout monitoring view(s)
- post-close tally view(s)
- published results page
- threshold calculations displayed clearly

---

## 7. Acceptance criteria
This bundle is complete when:
- students see only elections they are eligible for
- students cannot open another college's ballot through the backend
- students cannot submit more than one ballot per election
- selection limits are enforced in UI and backend
- turnout metrics are available during Active to authorized roles
- tally review is available only after Close to authorized roles
- final results are visible to eligible students only after Publish
- 50% + 1 thresholds display correctly

---

## 8. Suggested files and areas likely affected
Likely affected areas:
- student dashboard views/routes/templates or frontend pages
- ballot rendering logic
- ballot submission service/use-case
- election status checks
- results/tally views
- monitoring views
- tests for student voting and result visibility

---

## 9. Risks to avoid
- exposing another college's election in student flows
- accepting ballots for non-approved voters
- allowing duplicate submissions through refresh or repeated requests
- showing candidate-by-candidate tallies during Active voting
- exposing results before Publish

---

## 10. Manual test checklist
- approved student sees correct campus election during campus schedule
- approved student sees correct college election during own college schedule
- unapproved student can log in but cannot submit ballot
- student cannot see another college's election
- student can review ballot before submit
- student cannot submit the same election twice
- turnout counts update during Active
- authorized roles can review tallies after Close
- students can see final results only after Publish

---

## 11. Compact agent prompt template
```text
Read these docs as authoritative:
- docs/SYSTEM_SOURCE_OF_TRUTH.md
- docs/KNOWN_DECISIONS_COMPACT.md
- docs/BUNDLE_04_STUDENT_VOTING_RESULTS_AND_MONITORING.md

Implement Bundle 04 only.

Rules:
- students see only elections they are eligible for
- block cross-college access
- enforce one ballot per student per election
- no general live candidate tallies during Active
- final results visible to eligible students only after Publish
- show 50% + 1 thresholds according to frozen rules

Before coding, briefly list the files you plan to modify.
After coding, summarize:
- files changed
- migrations added if any
- tests added
- manual checks to run
```

