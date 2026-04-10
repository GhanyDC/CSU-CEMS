# Permission & Export Matrix

**Generated**: 2026-04-10 | **Source of Truth**: This document

---

## Admin Role Permission Matrix

### Election Setup Operations

| Operation | EB Head | Operator | Tally Watcher | AUDITOR | TECH_SUPPORT |
|-----------|---------|----------|---------------|---------|--------------|
| List elections | ✅ | ✅ | ✅ | ❌ | ❌ |
| View election detail | ✅ | ✅ | ✅ | ❌ | ❌ |
| Create election | ✅ | ✅ | ❌ | ❌ | ❌ |
| Delete election | ✅ | ✅ | ❌ | ❌ | ❌ |
| Add/Edit positions | ✅ | ❌ | ❌ | ❌ | ❌ |
| Reorder positions | ✅ | ❌ | ❌ | ❌ | ❌ |
| Delete positions | ✅ | ❌ | ❌ | ❌ | ❌ |
| Add/Edit candidates | ✅ | ✅ | ❌ | ❌ | ❌ |
| Upload candidate photos | ✅ | ✅ | ❌ | ❌ | ❌ |
| Import voter roll CSV | ✅ | ✅ | ❌ | ❌ | ❌ |
| Generate voter roll | ✅ | ✅ | ❌ | ❌ | ❌ |
| Finalize voter roll | ✅ | ❌ | ❌ | ❌ | ❌ |
| Start election | ✅ | ❌ | ❌ | ❌ | ❌ |
| Close election | ✅ | ❌ | ❌ | ❌ | ❌ |
| Publish results | ✅ | ❌ | ❌ | ❌ | ❌ |

### Monitoring Operations

| Operation | EB Head | Operator | Tally Watcher | AUDITOR | TECH_SUPPORT |
|-----------|---------|----------|---------------|---------|--------------|
| View turnout (Active+) | ✅ | ✅ | ✅ | ❌ | ❌ |
| View tally (Active) | ✅ Full | ✅ Redacted* | ❌ Blocked | ❌ | ❌ |
| View tally (Closed+) | ✅ Full | ✅ Full | ✅ Full | ❌ | ❌ |

*Redacted = participation summary only, no per-candidate vote counts

### Export Operations

| Export | Format | EB Head | Operator | Tally Watcher | Min State |
|--------|--------|---------|----------|---------------|-----------|
| Turnout CSV | CSV download | ✅ | ✅ | ✅ | Active |
| Turnout Text | JSON (clipboard) | ✅ | ✅ | ✅ | Active |
| Tally CSV | CSV download | ✅ | ❌ | ✅ | Closed |
| Participation CSV | CSV download | ✅ | ❌ | ❌ | Closed |
| Ballot Audit CSV | CSV download | ✅ | ❌ | ❌ | Closed |

---

## Export Content Detail

### Turnout CSV
```
Election Turnout Update
Election, <name>
Type, <type>
Status, <status>
Unofficial turnout update as of <timestamp>

Metric, Value
Total Registered/Approved Voters, <count>
Total Ballots Cast, <count>
Overall Turnout %, <pct>%

College, Eligible Voters
<college>, <count>
```

### Turnout Text (clipboard format)
```
UNOFFICIAL TURNOUT UPDATE
as of <date time>

Election: <name>
Type: <type>
Status: <status>

Total Registered Voters: <count>
Total Ballots Cast: <count>
Overall Turnout: <pct>%
```

### Tally CSV
```
Internal Canvassing / Tally Report
Election, <name>
...
Position, Category, Candidate, Party, College, Votes, Percentage, Winner, Abstain Count, Position Participation, Threshold Denominator, 50%+1 Threshold
```

### Participation CSV (Confidential)
```
Student ID, Full Name, College, Has Voted, Vote Timestamp
```
- Contains actual student identifiers — EB Head only
- Does NOT contain vote choices

### Ballot Audit CSV
```
Ballot ID, Hashed Voter ID (truncated), Timestamp, Position, Candidate Selected
```
- Student identities NOT recoverable from truncated hashes
- Links ballots to candidate selections anonymously

---

## Audit Trail

All exports create an `EXPORT_GENERATED` audit log entry containing:
- Admin username
- Export type
- Election name and ID
- Client IP and User-Agent
- Timestamp
