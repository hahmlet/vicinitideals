# Gresham GIS Preview

Standalone, quick-and-dirty web app for testing live Gresham parcel polygons against a few public overlay layers without wiring anything into the main `re-modeling` app.

## Run

Install the lightweight geometry helper once in the sandbox venv:

```powershell
c:/Users/Steph/Repos/ketch-media-ai/.venv/Scripts/pip.exe install shapely
```

Then from `re-modeling/`:

```powershell
c:/Users/Steph/Repos/ketch-media-ai/.venv/Scripts/python.exe tools/gresham_map_preview/app.py
```

Then open:

- `http://127.0.0.1:8010/`

## What it does

- looks up a parcel by address or APN from Gresham's public ArcGIS taxlot endpoint
- requests `returnGeometry=true` and `outSR=4326`
- draws the parcel on a Leaflet map
- queries a few live overlay layers that intersect the parcel:
  - City Zoning
  - Flood Plain
  - Open Space Overlay
  - Historic & Cultural Overlay
  - Hillside / Geologic Risk
  - Natural Resource Overlay

## Notes

- This is intentionally a **sandbox tool**, not part of the production UI.
- It is for visual/testing use only and should be treated as screening-grade.
- The flood badge now uses a simple overlap rule:
  - `>= 1%` of parcel area overlapped by the flood layer → `definitely_yes`
  - `> 0% and < 1%` → `maybe`
  - `0%` → `definitely_no`
