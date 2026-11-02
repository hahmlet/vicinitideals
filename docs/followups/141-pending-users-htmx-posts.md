# 141. Pending sign-ups can POST to FLATS forms over HTMX

[Copilot] Found 2026-11-01 by the security review of the lot tree marks (FOLLOWUPS 140, commit 8cf68c0f).
The onboarding guard in app/api/main.py (`onboarding_guard`, ~L470) waves every request carrying
`HX-Request: true` through, so a user who registered and is still PENDING (or has no org) reaches any
HTMX POST handler. The tree-mark routes now refuse such users themselves (`_teammate` in
app/api/routers/ui_flats.py), but the other FLATS write routes (/ui/flats/sign, sign-passage,
reading/rule, words/rule, triage/rule, check, flag decisions...) only check `_get_user(...) is None`.

FIX (build, a test can prove it): in the guard, an HTMX request from a signed-in user with no org or
PENDING membership gets 403 with an `HX-Redirect` header to /onboarding or /pending-approval instead of
being passed through; exempt paths stay exempt. Test in tests/api: a pending user's HTMX POST to
/ui/flats/sign and /ui/flats/lot-marks is refused, an active user's still works, /ui/onboarding HTMX
still works for a user with no org. Must not change: anything for ACTIVE users or anonymous visitors.
