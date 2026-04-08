# Bundle 02 — Core Election Domain and Official Voter Roll

Status: High-risk architecture bundle  
Recommended model use: **Use Plan mode once, then Agent mode**

---

## 1. Purpose
This bundle replaces the simplified voting foundation with proper election-specific structures and implements the official voter-roll pipeline.

This is the most important backend bundle because it defines what an election is, who may vote in it, and how one-ballot-per-election is enforced.

---

## 2. Why this bundle exists
The old simplified approach is not enough for real campus and college elections.

This bundle introduces:
- election-specific records
- election-specific voter eligibility
- one ballot per student per election
- support for multi-position ballots
- frozen approved voter rolls

---

## 3. Scope of this bundle
### In scope
- Election model
- Position model
- Candidate model refactor/extension as needed
- EligibleVoter model or equivalent approved-voter-per-election structure
- Ballot model
- BallotSelection model
- official voter-roll import/match/finalization pipeline
- counts overall and per college
- election-specific uniqueness/validation rules

### Out of scope
- polished admin dashboard UX
- full student-facing ballot pages
- final published results page
- advanced operational load testing

---

## 4. Frozen rules for this bundle
- Scope is campus + college only.
- College elections are separate election records, even when simultaneous.
- Official voter roll = registrar import filtered by verification form.
- Only approved voters may submit ballots.
- One student may cast:
  - one campus election ballot
  - one college election ballot for their own college
- The system must not rely on a single global `has_voted` flag for the new design.
- Campus and college election templates must be supported.
- Candidate qualification is handled outside the system.
- Candidate status should support active/inactive.

---

## 5. Recommended implementation direction
### Election domain
At minimum, the domain should support:
- `Election`
- `Position`
- `Candidate`
- `EligibleVoter`
- `Ballot`
- `BallotSelection`

### Voter roll pipeline
At minimum, the pipeline should support:
- registrar import source records
- verification-form source records
- matching by student ID, with birthdate validation or other explicit rule
- approved voter generation
- duplicate/unmatched tracking
- finalized/frozen voter roll for each election

### One-ballot-per-election enforcement
Use database-backed uniqueness where possible.

Recommended direction:
- unique ballot per `(election, student)` or `(election, voter identity key)`
- explicit relation between approved voter eligibility and ballot submission

---

## 6. Deliverables
Expected outputs:
- new/updated core election models
- migration strategy and migrations
- official voter-roll matching/finalization logic
- approved voter counts overall and per college
- one-ballot-per-election enforcement
- service-layer logic for election-specific eligibility checks
- tests for model behavior and vote/ballot rules

---

## 7. Acceptance criteria
This bundle is complete when:
- elections are modeled explicitly by type and scope
- positions support `max_selections_allowed`
- one ballot per student per election is enforceable
- a student cannot access another college's college election through the backend
- the system can show approved voter counts overall and per college
- voter rolls can be frozen before election start
- duplicate and unmatched import cases are tracked
- tests cover the new model constraints and submission rules

---

## 8. Suggested files and areas likely affected
Likely affected areas:
- elections models and services
- voting models and services
- candidate relations
- import utilities or management commands
- validation/service helpers
- migrations
- tests for elections, voting, and imports

---

## 9. Risks to avoid
- carrying forward the old global-vote assumption into the new design
- allowing college election visibility without college scoping
- allowing ballots for non-approved voters
- using only app-level checks without useful DB constraints
- unclear matching rules between registrar and verification records

---

## 10. Manual test checklist
- create one campus election and one college election record
- confirm CICS approved voter can be linked only to the CICS college election
- confirm non-approved voter cannot submit a ballot
- confirm same voter cannot submit two ballots for the same election
- confirm same voter can still have separate campus and college eligibility
- verify approved voter counts overall and per college
- verify duplicate and unmatched import cases are surfaced

---

## 11. Compact planning prompt template
```text
Read these docs as authoritative:
- docs/SYSTEM_SOURCE_OF_TRUTH.md
- docs/KNOWN_DECISIONS_COMPACT.md
- docs/BUNDLE_02_CORE_ELECTION_DOMAIN_AND_VOTER_ROLL.md

Task: Plan Bundle 02 only.

Do not redesign frozen election rules.
Do not build polished UI in this pass.

Produce:
1. final model direction
2. key relationships and constraints
3. migration strategy from current structure
4. voter-roll import/finalization flow
5. affected files/modules
6. tests to add
7. risks and edge cases
```

---

## 12. Compact agent prompt template
```text
Read these docs as authoritative:
- docs/SYSTEM_SOURCE_OF_TRUTH.md
- docs/KNOWN_DECISIONS_COMPACT.md
- docs/BUNDLE_02_CORE_ELECTION_DOMAIN_AND_VOTER_ROLL.md

Implement Bundle 02 only.

Rules:
- support campus + college elections only
- official voter roll = registrar import filtered by verification form
- enforce one ballot per student per election
- support separate simultaneous college election records
- do not add automatic candidate qualification logic

Before coding, briefly list the files you plan to modify.
After coding, summarize:
- files changed
- migrations added
- tests added
- manual checks to run
```

