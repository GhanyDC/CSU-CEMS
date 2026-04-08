# CEMS Implementation Roadmap

Status: Planning roadmap  
Purpose: This document translates the system source of truth into a practical phased implementation workflow for use with planning and coding models.

---

## 1. How to use this roadmap

This project should be implemented in phases.

Recommended working loop for each phase:
1. Read `SYSTEM_SOURCE_OF_TRUTH.md`
2. Use planning mode to refine the phase
3. Review the plan manually
4. Use implementation/agent mode for that single phase only
5. Run tests
6. Perform manual checks
7. Update completion notes
8. Move to the next phase only after the current one is stable

### Recommended model usage
- Use planning mode first for architecture, migrations, affected files, risks, and acceptance criteria.
- Use agent mode only after the phase plan is approved.
- Do not ask for full-system implementation in one prompt.

---

## 2. Recommended project documents

Maintain these files in the project folder:
- `SYSTEM_SOURCE_OF_TRUTH.md`
- `IMPLEMENTATION_ROADMAP.md`
- `KNOWN_DECISIONS.md`
- `PHASE_01_ADMIN_AUTH.md`
- `PHASE_02_CORE_ELECTION_MODELS.md`
- `PHASE_03_VOTER_ROLL_WORKFLOW.md`
- `PHASE_04_ADMIN_ELECTION_SETUP.md`
- `PHASE_05_STUDENT_DASHBOARD_AND_VOTING.md`
- `PHASE_06_RESULTS_AND_MONITORING.md`
- `PHASE_07_HARDENING_AND_DEPLOYMENT.md`
- `PHASE_COMPLETION_LOG.md`

---

## 3. Phase overview

### Phase 1 — Admin Authentication and Role-Based Access
Goal:
- create separate admin authentication
- implement role-based access
- protect sensitive election actions

Why first:
- all later admin workflows depend on secure admin identity separation

Core outputs:
- admin user model or role system
- separate admin login flow
- permission checks for Electoral Board Head, Operators, Tally Watchers, Auditors, Technical Support
- restriction of start/close/publish to Electoral Board Head only

Acceptance criteria:
- student login and admin login are separate
- only authorized roles can access admin pages
- only Electoral Board Head can start, close, publish, and finalize voter rolls
- audit logs capture admin logins and critical admin actions

Non-goals:
- full election setup UI
- student ballot flow

---

### Phase 2 — Core Election Domain Models
Goal:
- replace simplified voting assumptions with proper election-specific structures

Core outputs:
- Election model
- Position model
- Candidate updates/refactor
- EligibleVoter model
- Ballot model
- BallotSelection model
- migration strategy from current data model

Acceptance criteria:
- one ballot per student per election is enforceable
- multiple selections per ballot are supported
- campus and college elections are modeled separately
- positions have max selection rules

Non-goals:
- polished admin UX
- final results UI

---

### Phase 3 — Official Voter Roll Workflow
Goal:
- implement registrar import filtered by verification form

Core outputs:
- registrar import process
- verification-form import process
- record matching rules
- duplicate/unmatched reporting
- official voter-roll finalization
- approved voter counts overall and per college

Acceptance criteria:
- the system can show imported count, verified count, approved count, unmatched records, and duplicate records
- voter roll can be frozen for an election
- only approved voters are eligible to submit ballots

Non-goals:
- advanced candidate workflows

---

### Phase 4 — Admin Election Setup Flow
Goal:
- make election setup understandable to non-technical users

Core outputs:
- Create Campus Election flow
- bulk Create College Elections flow
- template-generated positions
- candidate management in Draft state
- readiness checklist screen

Acceptance criteria:
- campus elections can be created from template
- 9 college elections can be bulk-created from template
- no UUID entry is required in normal setup flow
- candidates can be assigned to valid positions while election is in Draft

Non-goals:
- final student-facing results page

---

### Phase 5 — Student Dashboard and Ballot Submission
Goal:
- let eligible students see and submit the correct election ballots

Core outputs:
- student dashboard eligibility logic
- campus election visibility rules
- college election filtering by student college
- ballot rendering by position
- review and submit flow
- atomic ballot submission with duplicate prevention

Acceptance criteria:
- students see only elections they are allowed to vote in
- a student cannot see another college's election
- a student cannot submit more than one ballot per election
- invalid selection counts are blocked both in UI and backend

Non-goals:
- public results page

---

### Phase 6 — Results, Monitoring, and Visibility Controls
Goal:
- support turnout monitoring, closed-state tally review, and publish-state public results

Core outputs:
- admin turnout dashboards
- tally watcher views
- closed-state tally review
- published results page for eligible students
- 50% + 1 calculations and threshold display

Acceptance criteria:
- live candidate tallies are not exposed during Active unless later approved
- authorized roles can review tallies after Close
- eligible students can see final results only after Publish
- turnout and threshold basis are displayed correctly

Non-goals:
- deep infrastructure hardening

---

### Phase 7 — Hardening, Concurrency, and Deployment Readiness
Goal:
- reduce operational risk before live election use

Core outputs:
- PostgreSQL concurrency testing
- audit expansion
- load testing plan/results
- backup and restore rehearsal
- deployment checklist
- election-day runbook

Acceptance criteria:
- concurrency behavior is validated on PostgreSQL
- backup/restore has been rehearsed
- deployment plan is documented
- dry-run mock election is completed

Non-goals:
- major feature redesigns unless critical blockers are found

---

## 4. Suggested execution order

Recommended order:
1. Phase 1 — Admin Authentication and Role-Based Access
2. Phase 2 — Core Election Domain Models
3. Phase 3 — Official Voter Roll Workflow
4. Phase 4 — Admin Election Setup Flow
5. Phase 5 — Student Dashboard and Ballot Submission
6. Phase 6 — Results, Monitoring, and Visibility Controls
7. Phase 7 — Hardening, Concurrency, and Deployment Readiness

Reason:
- secure admin identity first
- correct election data model second
- eligibility pipeline third
- admin UX after the core rules exist
- student flow only after the backend rules are stable

---

## 5. Prompting pattern for planning mode

For each phase, the planning prompt should contain:

### A. Current reality
Explain what currently exists and what is missing.

### B. Phase objective
Define what must be completed in this phase only.

### C. Frozen rules
Restate decisions that must not change.

### D. Required deliverables
Ask for:
- proposed architecture
- affected files
- migrations
- risks
- acceptance criteria
- test plan

### E. Constraints
State what must be preserved and what must be avoided.

---

## 6. Prompting pattern for agent mode

After a planning output is approved, the implementation prompt should include:
- the approved phase plan
- the relevant excerpt from `SYSTEM_SOURCE_OF_TRUTH.md`
- exact scope of implementation
- request for minimal but complete changes
- request for updated tests
- request for a short completion report

Important rule:
- agent mode should implement one phase only
- do not combine multiple major phases in one implementation prompt

---

## 7. Suggested phase-file structure

Each phase file should contain:
- Phase name
- Goal
- Scope
- Frozen rules relevant to this phase
- Affected models/pages/services
- Acceptance criteria
- Non-goals
- Risks
- Manual testing checklist
- Notes for the next phase

---

## 8. Manual review checklist after every phase

After each implementation phase, review:
- did the changes follow the source of truth?
- were any frozen rules changed without approval?
- were any shortcuts introduced that weaken election integrity?
- were role restrictions preserved?
- were tests added or updated?
- does the UI remain understandable to non-technical users?
- were audit logs kept or improved?

---

## 9. Recommended testing rhythm

After each phase:
1. run automated tests
2. perform manual tests for the new workflow
3. review edge cases
4. log findings
5. fix critical issues before advancing

Before live deployment:
- run a full mock election
- test wrong-college access
- test duplicate submission attempts
- test close-while-submitting behavior
- test publish visibility rules
- test lone-candidate threshold calculations

---

## 10. Initial risks to watch throughout implementation

High-risk drift areas:
- reverting to a global has-voted design
- exposing UUIDs in normal admin workflows
- accidentally allowing live candidate tallies during Active voting
- mixing student and admin authentication flows
- allowing operators to perform Vice President-only actions
- making the system decide candidate qualification
- allowing voting before voter-roll finalization
- failing to scope college elections correctly

---

## 11. Completion logging rule

After each phase, append to `PHASE_COMPLETION_LOG.md`:
- date
- phase name
- summary of what was implemented
- major files added/changed
- test status
- known issues
- follow-up actions

This log becomes the practical reference for the next prompt.

---

## 12. Immediate next step

The next implementation step is:

**Phase 1 — Admin Authentication and Role-Based Access**

Before coding begins, create:
- `PHASE_01_ADMIN_AUTH.md`
- `KNOWN_DECISIONS.md`

Then use planning mode first.

