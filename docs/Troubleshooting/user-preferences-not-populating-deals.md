# User Preferences Not Populating Into New Deals

**Symptom:** User sets a preference in My Preferences (e.g., Hold/Loan Term = 30 years) but when creating a new deal and reaching Step 4 (Debt Terms) in the Deal Setup Wizard, the field still shows a different value (e.g., 10 years).

---

## What Went Wrong

The wizard has two server-side handlers:

- **GET handler** — renders a step when the user navigates directly to it (e.g., hitting the Back button or opening the wizard fresh)
- **POST handler** — processes a submitted step and renders the *next* step inline

The code that seeds user/org preference values into the wizard staging area (the `debt_terms` JSONB column) only existed in the **GET handler**. When the user clicked "Next" from Step 3, the **POST handler** rendered Step 4 directly — without ever running the seeding logic. The Jinja2 template then fell back to a hardcoded `or 10` default for `hold_term_years`, completely ignoring the user's preference.

The same bug existed for `amort_years` (amortization term) and was previously fixed by adding seeding to the GET handler. That fix worked when users navigated backwards or opened the wizard at Step 4 directly, but not when stepping forward through the wizard normally.

Additionally, the Jinja2 template fallback was hardcoded as `or 10`, which is not the system baseline (7). This meant even if seeding failed for another reason, the wrong fallback was shown.

---

## What Was Tried

1. Confirmed the GET handler had correct seeding logic that resolved user/org preferences and populated `debt_terms["permanent_debt"]["hold_term_years"]` — this worked on direct navigation/Back.
2. Confirmed `resolve_all_defaults()` was correctly returning the user's saved preference (30).
3. Traced the POST → render-next-step flow and found the seeding block was entirely absent from the POST handler.

---

## What Fixed It

**`app/api/routers/ui.py`**

Extracted the seeding logic into a reusable helper function `_seed_wizard_perm_defaults(inputs, session, request)`. Called it from both:
- The GET handler (existing path — Back button / direct navigation)
- The POST handler (new addition — "Next" button flow), after `session.refresh()` and before rendering the next step template

**`app/templates/partials/deal_setup_wizard.html`**

Changed the Jinja2 fallback from:
```jinja2
{%- set _hold_term = _dt_cfg.get('hold_term_years') or 10 -%}
```
to:
```jinja2
{%- set _hold_term = _dt_cfg.get('hold_term_years') if _dt_cfg.get('hold_term_years') is not none else 7 -%}
```

This uses the correct system baseline (7) as last-resort fallback, and avoids the Jinja2 `or` operator treating falsy values (0, empty string) as missing.

---

## Affected Fields

Same pattern applies to any field seeded in `_seed_wizard_perm_defaults`. Currently:
- `hold_term_years` (Hold / Loan Term, years)
- `amort_years` (Amortization Term, years)

If more fields are added to wizard seeding in the future, add them to the `for _def_key, _staging_key in (...)` loop in `_seed_wizard_perm_defaults()` and they will work in both GET and POST flows automatically.

---

## Note on Existing Deals

This fix applies to **new deals going through the wizard for the first time**. For deals that previously completed the wizard (and had `hold_term_years: 10` baked into an existing `CapitalModule`), the wizard mirrors the module's stored value back into staging on open — which takes precedence over the user preference seeding. Changing the hold term on an existing deal requires editing it directly in the wizard or model builder.

**Commit:** `e9322de` — `fix(wizard): seed perm-debt defaults in POST handler, not just GET`
