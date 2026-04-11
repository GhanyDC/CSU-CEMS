# STUDENT HARDENING — RESPONSIVE AND STATE NOTES 01

**Date:** 2026-04-10  
**Scope:** Student-side UI (login, dashboard, ballot, results)

---

## 1. Responsive Layout Decisions

### Breakpoints Used

| Breakpoint | Target | Key Changes |
|-----------|--------|-------------|
| ≤ 576px | Phones | Cards single-column, review stacks vertically, submit full-width, results compact |
| ≤ 768px | Tablets | Ballot container reduced padding, 2-column candidate grid |
| > 768px | Desktop | Full 3-column candidate grid, side-by-side review layout |

### Ballot Page Responsive Behavior

**Desktop (>768px)**
- Candidate cards in 3-column grid (`repeat(auto-fill, minmax(200px, 1fr))`)
- Review section: position label and value side-by-side
- Submit button: auto-width centered
- Comfortable spacing: `2rem` container padding

**Tablet (577px–768px)**
- Candidate cards in 2-column grid
- Review section: still side-by-side
- Reduced container padding: `1rem`
- Submit button: still auto-width

**Mobile (≤576px)**
- Candidate cards stack to single column (min-width reduced to `140px`)
- Candidate card padding reduced to `0.75rem`
- Review section: label stacks above value (flex-direction: column)
- Review label takes full width with bottom margin
- Submit button: full width (`width: 100%`)
- Position counter badges stay inline with position title

### Results Page Responsive Behavior

**Mobile (≤576px)**
- Category badges wrap (flex-wrap enabled)
- Vote result bars maintain minimum readable width
- Winner badges stay visible
- Photo containers shrink proportionally

### Dashboard Responsive Behavior

- Bootstrap grid handles column stacking natively
- Status cards auto-stack on small screens
- Election cards remain full-width on all breakpoints

---

## 2. Desktop vs. Mobile Behavior Differences

| Feature | Desktop | Mobile |
|---------|---------|--------|
| Candidate grid | 3 columns | 1 column |
| Card interaction | Click | Tap (same handler) |
| Review layout | Side-by-side | Stacked vertically |
| Submit button | Auto-width | Full-width |
| Toast position | Top-right | Top-center (Bootstrap default) |
| Success modal | Centered, 500px max | Full-width with margins |
| Photo size | Standard | Slightly smaller |

### Touch Interaction Notes

- No hover-dependent interactions (all click/tap based)
- Card selection uses `click` event (works for both mouse and touch)
- Keyboard accessible: `tabindex="0"` on cards, Enter/Space handlers
- No drag, long-press, or swipe interactions required
- Bootstrap toast handles mobile positioning automatically

---

## 3. State Synchronization Notes

### The Root Cause of the Review/Submit Sync Bug

**Before (Broken):**
```
User interaction → DOM manipulation → Query DOM for state → Update review
                                        ↑
                              Failed here: querySelectorAll matched
                              abstain checkbox, .closest('.candidate-card')
                              returned null, TypeError crashed execution
```

**After (Fixed):**
```
User interaction → Update ballotState Map → syncUI() renders everything
                                               ├── Card visual state
                                               ├── Counter badges
                                               └── Review section
```

### State Architecture Invariants

1. **ballotState is the single source of truth** — no state is stored in the DOM
2. **syncUI() is idempotent** — calling it multiple times produces the same output
3. **No partial updates** — every user action calls `syncUI()` which updates everything
4. **Submit payload is built from ballotState**, never from DOM queries
5. **Review section is read-only output** — it has no interactive elements, only displays state
6. **Counter badges are derived from state** — `candidates.size` or `abstain` flag

### State Consistency Guarantees

| Scenario | Guarantee |
|----------|-----------|
| Rapid clicking | Each click fully completes state+UI update before next |
| Mixed selection patterns | Mutual exclusivity (candidate vs abstain) enforced at state level |
| Network error during submit | State preserved, button re-enabled, user can retry |
| Session expiry during submit | Banner shown, redirect pending, no stale state |
| Browser back after submit | ballotState is in-memory only, page reload resets everything |

### Why Map + Set (Not Array/Object)

- `Map` preserves insertion order (positions render in API order)
- `Map.has()` / `Map.get()` are O(1) for position lookup
- `Set` for candidates gives O(1) add/delete/has with no duplicates
- Both are reference types; `syncUI()` reads current state without copying
- `Set.size` gives instant count for counter badges

---

## 4. Error-Handling Notes

### Error Categories and Responses

| Error | HTTP Code | User-Facing Response | Recovery |
|-------|-----------|---------------------|----------|
| Session expired | 401 | Yellow banner at top: "Session expired" | Auto-redirect to login after 3s |
| Election closed | 403 (specific) | "Election is no longer active" alert | "Back to Dashboard" button |
| Already voted | 409 | "Already submitted for this election" | Auto-redirect to dashboard after 3s |
| Network failure | 0 / timeout | "Network error. Please check your connection" toast | Submit button re-enabled |
| Server error | 500 | "Something went wrong. Please try again" toast | Submit button re-enabled |
| Ballot empty | N/A (client) | "Please vote for at least one candidate" toast | No network call made |
| Not eligible | 403 (general) | "Not eligible for this election" alert | "Back to Dashboard" button |

### Error-Handling Design Decisions

1. **401 always means session expired** — student auth uses sessions, not tokens
2. **409 is always duplicate vote** — only one action per student per election
3. **Submit button is re-enabled only for recoverable errors** (network, 500)
4. **Submit button stays disabled for terminal errors** (409, 401, 403)
5. **No error codes shown to users** — all messages are human-friendly
6. **Console errors logged for debugging** but not displayed in UI

### Fetch Wrapper Pattern

```javascript
try {
    const response = await fetch(url, options);
    if (response.status === 401) return showSessionExpired();
    if (response.status === 409) return handleDuplicate();
    if (!response.ok) throw new Error(response.statusText);
    return await response.json();
} catch (err) {
    showToast('Network error. Please try again.', 'danger');
    throw err;
}
```

---

## 5. Privacy and Shared-Device Notes

### Design Constraints

CEMS is used on **shared campus computers** and **students' personal phones**. Privacy considerations:

| Concern | Mitigation |
|---------|-----------|
| Next user sees votes | Success modal does NOT show individual selections |
| Browser history reveals votes | No vote data in URL parameters |
| Session persistence | Session-based auth, explicit logout available |
| Screen shoulder-surfing | Confirmation shows only ballot ID, not choices |
| Shared device logout | Dashboard has prominent logout button |
| Results don't reveal individual votes | Only aggregate counts shown |

### Session Management

- Sessions are server-side (Django default)
- Session cookie is `httponly` and `samesite=Lax`
- Session expires based on Django settings
- Client detects expired session on any 401 response
- No "remember me" option (intentional for shared devices)
- Logout clears server session + client redirect

### Ballot Anonymization

- Ballot ID is a salted SHA-256 hash: `SHA256(election_id + student_id + per_election_salt)`
- Same student always gets same ballot ID for same election (enables duplicate detection)
- Ballot ID cannot be reversed to student identity
- Salt is unique per election (prevents cross-election correlation)
- Admin cannot map ballot ID → student

---

## 6. Tradeoffs and Limitations

### Known Tradeoffs

| Decision | Tradeoff | Rationale |
|----------|----------|-----------|
| Vanilla JS (no framework) | More manual DOM management | Zero bundle size, no build step, fast load |
| In-memory ballotState | Lost on page reload | Intentional — no cached vote state on shared devices |
| No offline support | Must have network to vote | Election integrity requires server validation |
| No real-time updates | Student won't see election close in real-time | Simplicity; election transitions are admin-controlled |
| Toast for errors (not inline) | May be missed on scroll | Bootstrap convention; positioned at top of viewport |
| Static backdrop modal | Can't dismiss accidentally | Intentional for confirmation screen |

### Current Limitations

1. **No WebSocket support** — if election closes while student is on ballot page, they learn only on submit (403)
2. **No auto-save** — partial ballot is not persisted; if browser crashes, selections are lost
3. **No dark mode** — CSS variables support it but not implemented
4. **No i18n** — all strings are English-only
5. **No image lazy loading** — all candidate photos load eagerly (acceptable for typical ballot sizes)
6. **No PWA features** — no service worker, no offline cache
7. **Counter badge does not animate** — state change is instant (no CSS transition on badge text)

### Future Considerations

- **Real-time election status**: WebSocket or polling to detect closed elections
- **Biometric/2FA**: For higher-stakes elections
- **Accessibility audit**: WCAG 2.1 AA compliance for screen readers
- **Dark mode toggle**: CSS variable swap
- **Print ballot receipt**: Post-submission PDF with ballot ID only (no selections)
