# UX Flows

**Status:** Implemented · Screens in `frontend/lib/features/*/presentation`

## Design principles
Calm, professional, accessible. High contrast, large readable type, minimal
decorative animation (page transitions ≤ 350ms; no looping background
animations in task flows). Emojis allowed only as decorative accents next to
text labels — never as the only carrier of meaning. Safety information is
always visible textually, never hidden behind interactions.

## Primary flows

### 1. First run → consent → account
```
Splash → Onboarding (3 slides, no medical claims)
       → Consent screen (what app does/does not, data collected,
          clinician disclaimer; Accept/Decline → decline exits)
       → Register → Home
```
Consent version is sent to the backend and stored.

### 2. Returning user
```
Splash → (secure token) → Home   (token invalid → Login)
```

### 3. Dashboard (Home)
Sections in order:
1. **TODAY** — today's meal ideas (from current plan's matching day),
   completed-meal toggles, observed nutrition totals.
2. **NEXT CHECK-IN** — next health check-in date derived from last record
   (monthly cadence) with a "Log health data" action.
3. **MEAL IDEAS** — safe suggestions from the latest plan.
4. **MY PREFERENCES** — dietary preference, allergies (category chips),
   edit → /preferences.
5. **SHARE WITH CLINICIAN** — builds the clinician summary (share sheet /
   copy to clipboard).
6. **URGENT HELP** — visually separated card with warning icon, opens the
   urgent-help screen (deliberately not a bottom tab).

Every section has LOADING / EMPTY / ERROR+RETRY states.

### 4. Health data entry
Form validates **before** submit: week 1–42, trimester auto-derived from
week (single source: same boundaries as backend), weight required, optional
BP/Hb/glucose left blank if unknown (no fabricated defaults), allergies as
multi-select chips (fixed category list). On submit:
- 422 contradiction → inline message naming the invalid pair.
- 409 CONSENT_REQUIRED → routes to consent screen.
- Success → optional plan generation with progress state.

### 5. Meal plan → detail → swap
```
Plan (7-day tabs: Day 1…7) → day view with 4 slots
  → meal card "Why suggested" expandable
  → Meal detail (image, serving, ingredients, nutrition, allergens,
    safety notes, prep, source + evidence version, substitutions,
    Swap button)
  → Swap: new meal same slot, same safety filters, explanation shown
```

### 6. Urgent help
```
Dashboard card → Urgent Help screen:
  1. "This app cannot assess emergencies." (prominent)
  2. Warning signs list (contact clinician / call emergency services)
  3. Regional emergency guidance (India: 112 / 108 / 104)
  4. "Share with clinician" action + personal observation note
```
No "mark as resolved" control exists anywhere in this flow.

### 7. Profile & privacy
Profile → edit (PATCH; success snackbar only on backend 200) → language
switcher (5 languages) → Privacy section: export data (share/download),
delete account (confirm dialog), logout, logout-all-devices.

## Error/offline states (all screens)
| State | Presentation |
|---|---|
| Loading | Centered quiet spinner + message (no lottie loops) |
| Empty | Icon + one-line explanation + primary action |
| Error | Icon + short message + RETRY button |
| Offline | Banner + cached read-only meal data where available |
| Session expired | Snackbar + redirect to login |

## Navigation map
Bottom tabs: Home · Meal Plan · Urgent Help (styled distinctly) · Profile —
Urgent Help keeps a tab for reachability but is visually separated and opens
the informational screen only.
