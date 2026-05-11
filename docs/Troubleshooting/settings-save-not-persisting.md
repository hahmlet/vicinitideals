# Settings Page: Save Not Persisting

## Symptom

User changes a field on `/settings/preferences` or `/settings/org`, clicks Save, refreshes — value reverts to the default. No visible error on the page.

## Root Cause

**Double-mounted router prefix.** `main.py` includes all routers from `ROUTERS` with `prefix="/api"`. If a router also declares `prefix="/api/settings"`, the resulting paths land at `/api/api/settings/...` — 404 on every save, silently.

HTMX swaps the 404 response body into the target div. If the target div is small or hidden, the user sees nothing and assumes the save succeeded.

## Diagnosis

Check the API logs immediately after clicking Save:

```bash
docker logs vicinitideals-api --tail=50 2>&1 | grep -E "settings|PUT|404"
```

Expected (broken): `PUT /api/settings/user/hold_term_years 404 Not Found`  
Expected (working): `PUT /api/settings/user/hold_term_years 200 OK`

## Fix

In `app/api/routers/settings.py`, the router prefix must be `/settings` (not `/api/settings`):

```python
# Wrong — main.py adds /api, resulting in /api/api/settings/...
router = APIRouter(prefix="/api/settings", tags=["settings"])

# Correct
router = APIRouter(prefix="/settings", tags=["settings"])
```

## Convention

All routers in `ROUTERS` (`app/api/routers/__init__.py`) get `/api` prepended by `main.py`. Router-level prefixes must NOT include `/api`. The UI router (`ui.py`) is included separately without the `/api` prefix and is the exception.

---

## Secondary Fixes Applied in Same Session

### Auth: `CurrentUserId` dependency didn't accept session cookies

`get_current_user_id` in `deps.py` only read `X-User-ID` header or `request.state.user_id`. Browser HTMX form submissions carry neither — they use the signed `vd_session` cookie. Added cookie fallback:

```python
async def get_current_user_id(request, x_user_id=None):
    candidate = getattr(request.state, "user_id", None) or x_user_id
    if candidate:
        return UUID(str(candidate))
    # Fallback for browser HTMX requests
    from app.api.auth import COOKIE_NAME, decode_session_token
    token = request.cookies.get(COOKIE_NAME)
    if token:
        uid = decode_session_token(token)
        if uid is not None:
            return uid
    raise HTTPException(status_code=401, detail="Authentication required")
```

### Scroll: Settings pages not scrollable below the fold

`.main` in `app.css` uses `overflow: hidden`. Settings templates inject content directly into `.main` with no scroll container. Fix: wrap `{% block content %}` body in a scrollable flex child:

```html
<div style="flex:1;overflow-y:auto;min-height:0">
  <!-- page content -->
</div>
```

Apply to any page template that puts tall content directly inside `{% block content %}` without using the `.content` CSS class.
