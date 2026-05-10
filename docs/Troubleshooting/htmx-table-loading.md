# Troubleshooting: HTMX Tables Go Empty (Opportunities Page)

**Symptom:** One or more of the three opportunity tables (Active Deals, Off Market, On Market) show blank rows or "No records" after a deploy, despite data existing in the database.

**Affected file:** `app/templates/opportunities.html`

---

## Root Causes Encountered (in order, May 2026)

### 1. `hx-trigger` with `from:` cross-element syntax silently drops all triggers

**What happened:** The tbodies had:
```html
hx-trigger="load, input delay:400ms from:#opp-filters, change from:#opp-filters"
```
HTMX 1.9.12 failed to parse the `from:` qualifier and **silently dropped the entire trigger string**, including `load`. No requests were ever made.

**Symptom:** All three table counts showed `—` (never updated from initial state). No requests visible in server logs.

**Fix:** Never use `from:` in `hx-trigger`. Use a custom event dispatched via JS instead, or drive loading from JS entirely (see fix #4 below).

---

### 2. `hx-trigger="load"` + `hx-include` on initial-HTML elements does not fire

**What happened:** After switching to `hx-trigger="load, oppFilterChange"` with `hx-include="#opp-filters"`, the `load` trigger did not fire on page initialization. HTMX 1.9.x does not reliably fire the `load` trigger for elements already in the original HTML when `hx-include` points to an external element.

**Symptom:** Counts showed `—`, no requests in server logs.

**Fix:** Do not rely on `hx-trigger="load"` + `hx-include` together on initial-HTML elements. See fix #4.

---

### 3. Empty number inputs cause FastAPI 422 errors

**What happened:** Using `new URLSearchParams(new FormData(form))` to build request params included empty number inputs: `min_units=&max_units=`. FastAPI tried to parse these as `int` and returned HTTP 422.

**Symptom:** Counts showed `0` (not `—`), rows empty — endpoint was reached but returned no usable HTML. On Market showed 0 despite 228 DB rows.

**Fix:** Filter empty values before appending to `URLSearchParams`:
```javascript
new FormData(form).forEach(function(v, k) { if (v !== '') qs.append(k, v); });
```

---

### 4. `htmx.ajax()` silently fails for 2nd and 3rd simultaneous calls

**What happened:** After switching to `document.addEventListener('DOMContentLoaded', loadAll)` using `htmx.ajax()`, the Deals table loaded correctly (1 row) but Off Market and On Market remained empty.

**Symptom:** Deals count = correct, Off Market and On Market counts = `0`. Server logs showed no requests for the failing endpoints.

**Root cause:** `htmx.ajax()` appears to silently fail when called multiple times in rapid succession during DOMContentLoaded. The deals call succeeded; the other two did not.

**Fix:** Switch from `htmx.ajax()` to native `fetch()` + `htmx.process()`. Call `htmx.process(el)` after setting `innerHTML` to activate HTMX attributes (star buttons, etc.) in newly loaded rows:

```javascript
fetch(url, {credentials: 'same-origin'})
  .then(function(r) { return r.text(); })
  .then(function(html) {
    el.innerHTML = html;
    if (window.htmx) htmx.process(el);
    updateCounts();
  });
```

---

## Current Working Pattern (as of May 2026)

Tbodies are plain empty elements — no HTMX attributes:
```html
<tbody id="deals-tbody"></tbody>
<tbody id="offmarket-tbody"></tbody>
<tbody id="onmarket-tbody"></tbody>
```

JS in the page drives all loading:
```javascript
var tables = [
  {id: 'deals-tbody',     url: '/ui/opportunities/rows/deals'},
  {id: 'offmarket-tbody', url: '/ui/opportunities/rows/offmarket'},
  {id: 'onmarket-tbody',  url: '/ui/opportunities/rows/onmarket'},
];

function loadAll() {
  var form = document.getElementById('opp-filters');
  var qs = new URLSearchParams();
  if (form) {
    new FormData(form).forEach(function(v, k) { if (v !== '') qs.append(k, v); });
  }
  var params = qs.toString();
  tables.forEach(function(t) {
    var el = document.getElementById(t.id);
    if (!el) return;
    fetch(t.url + (params ? '?' + params : ''), {credentials: 'same-origin'})
      .then(function(r) { return r.text(); })
      .then(function(html) {
        el.innerHTML = html;
        if (window.htmx) htmx.process(el);
        updateCounts();
      });
  });
}

document.addEventListener('DOMContentLoaded', loadAll);

// Re-fire on filter form changes
document.addEventListener('DOMContentLoaded', function() {
  var form = document.getElementById('opp-filters');
  if (!form) return;
  var timer;
  form.addEventListener('input', function() { clearTimeout(timer); timer = setTimeout(loadAll, 400); });
  form.addEventListener('change', function() { clearTimeout(timer); loadAll(); });
});
```

---

## Debugging Checklist

If tables go empty again:

1. **Check server logs** — are requests to `/ui/opportunities/rows/*` hitting the server at all?
   ```bash
   docker logs vicinitideals-api --tail 50 | grep opportunities
   ```

2. **Check DB directly** — does data exist for the expected query?
   ```sql
   SELECT promotion_source, archived, COUNT(*) FROM opportunities GROUP BY 1, 2;
   ```

3. **Check for 422 errors** — open browser DevTools → Network → filter for `rows` → check response status. 422 = bad query params (probably empty number inputs getting through).

4. **Check `archived` column values** — `Opportunity.archived.is_(False)` matches `FALSE` only (not NULL). Run:
   ```sql
   SELECT archived, COUNT(*) FROM opportunities GROUP BY archived;
   ```
   If NULLs appear, change filter to `Opportunity.archived != True`.

5. **Check JS errors in browser console** — any uncaught exception in the `loadAll` IIFE stops all three fetches.

6. **Check HTMX version** — this page's loading pattern was designed around the limitations of HTMX 1.9.12 (loaded with `defer` in `base.html`). If HTMX is upgraded, re-test `load` trigger behavior on initial-HTML elements.
