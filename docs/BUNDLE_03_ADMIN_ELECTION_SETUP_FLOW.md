# Bundle 03 — Admin Election Setup Flow

Status: Workflow/UI bundle  
Recommended model use: **Usually Agent mode after architecture is frozen**

---

## 1. Purpose
This bundle makes election setup understandable and efficient for non-technical election administrators.

It should convert technical or low-level setup steps into a guided admin workflow.

---

## 2. Why this bundle exists
The admin side should not require UUID entry, shell commands, or developer-only knowledge.

This bundle creates a template-driven setup process for:
- campus elections
- simultaneous college elections
- candidate assignment
- readiness review

---

## 3. Scope of this bundle
### In scope
- admin election creation screens or flows
- campus election template generation
- bulk creation of college elections
- candidate management in Draft state
- readiness/review checklist
- admin visibility of approved voter counts overall and per college
- VP-only action buttons visible at the correct times

### Out of scope
- student ballot UI
- public results page
- deep infrastructure work

---

## 4. Frozen rules for this bundle
- Non-technical admins should never have to input UUIDs manually.
- Election creation must be button-based and template-driven.
- Campus elections and college elections use separate schedules.
- College elections happen simultaneously.
- Campus election template:
  - President — choose 1
  - Vice President — choose 1
  - Senators — choose up to 12
  - College Representatives — according to the constitution
  - Party-list Representatives — according to the constitution
- College election template:
  - Governor — choose 1
  - Vice Governor — choose 1
  - Board Members — choose up to 8
- Candidate qualification is not system-decided.
- Candidate status should support active/inactive.
- Candidate lists are editable in Draft and locked in Active.
- Only Electoral Board Head may start, close, or publish.

---

## 5. Recommended implementation direction
### Election creation flow
Provide two clear entry points:
- Create Campus Election
- Create College Elections

### Bulk college election generation
Preferred behavior:
- admin chooses the shared schedule
- system creates separate election records for all selected colleges
- system pre-populates college positions automatically

### Candidate management
Preferred behavior:
- assign candidate to election + position
- manage Active/Inactive status
- lock edits when election becomes Active

### Review screen
Show a readiness checklist before start:
- voter roll finalized
- positions complete
- candidates complete
- schedule set
- unresolved issues count
- approved voter counts overall and per college
- lone-candidate flags if useful

---

## 6. Deliverables
Expected outputs:
- create-campus-election flow
- bulk-create-college-elections flow
- template-generated positions
- candidate management screen/flow for Draft elections
- readiness/review screen
- admin restriction logic consistent with roles

---

## 7. Acceptance criteria
This bundle is complete when:
- admins can create a campus election without developer-only inputs
- admins can bulk-create the college elections for the selected colleges
- templates generate the correct positions
- candidate assignment is limited to valid positions
- candidate edits are blocked when election becomes Active
- review screen shows readiness and counts clearly
- only Electoral Board Head can trigger start/close/publish

---

## 8. Suggested files and areas likely affected
Likely affected areas:
- admin panel views/routes/templates or admin UI components
- election creation services
- candidate management services
- review/checklist utilities
- permission guards
- tests for admin election-setup flows

---

## 9. Risks to avoid
- forcing admins to create positions manually every time
- exposing raw UUIDs in normal workflows
- allowing Active-election candidate edits by mistake
- mixing campus and college setup in confusing ways
- letting Operators perform VP-only actions

---

## 10. Manual test checklist
- Operator can create a campus election draft
- Operator can bulk-create college election drafts
- correct positions appear for campus election
- correct positions appear for each college election
- candidate can be assigned only to valid positions
- candidate can be set inactive in Draft
- election review shows approved voter counts
- Operator cannot start election
- Electoral Board Head can start election

---

## 11. Compact agent prompt template
```text
Read these docs as authoritative:
- docs/SYSTEM_SOURCE_OF_TRUTH.md
- docs/KNOWN_DECISIONS_COMPACT.md
- docs/BUNDLE_03_ADMIN_ELECTION_SETUP_FLOW.md

Implement Bundle 03 only.

Rules:
- make setup understandable for non-technical admins
- do not expose UUIDs in normal flows
- use template-driven election creation
- support bulk creation of simultaneous college elections
- candidate edits must be locked once election is Active
- respect VP-only start/close/publish

Before coding, briefly list the files you plan to modify.
After coding, summarize:
- files changed
- migrations added if any
- tests added
- manual checks to run
```

