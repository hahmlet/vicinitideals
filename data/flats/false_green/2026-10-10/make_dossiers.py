"""Turn dossiers.jsonl (read-only SELECT out of the live DB, run 70) into one
readable text file and one picture per lot. Reading aid only; no rule touched."""
import json, sys, pathlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely.geometry import shape, Polygon

here = pathlib.Path(__file__).parent
work = here / "work"
out_txt = work / "lots"; out_png = work / "pics"
out_txt.mkdir(exist_ok=True); out_png.mkdir(exist_ok=True)

def slim(x):
    if isinstance(x, dict):
        return {k: slim(v) for k, v in x.items() if k not in ("drawing",)}
    if isinstance(x, list):
        return [slim(v) for v in x]
    return x

def poly(coords):
    try:
        return Polygon(coords)
    except Exception:
        return None

for line in open(work / "dossiers.jsonl"):
    d = json.loads(line)
    slug = d["jurisdiction"].split("/")[-1] + "_" + "".join(c if c.isalnum() else "-" for c in d["tlid"])
    lot = shape(d["geom"])
    fig, ax = plt.subplots(figsize=(9, 9))
    for n in d["neighbours"] or []:
        g = shape(n["geom"])
        for p in (g.geoms if hasattr(g, "geoms") else [g]):
            x, y = p.exterior.xy
            ax.plot(x, y, color="#999", lw=0.7)
        c = g.representative_point()
        ax.text(c.x, c.y, f"{n['zone'] or ''}\n{(n['addr'] or '')[:18]}", fontsize=5, color="#666", ha="center")
    for p in (lot.geoms if hasattr(lot, "geoms") else [lot]):
        x, y = p.exterior.xy
        ax.plot(x, y, color="k", lw=2)
    greens = [r for r in d["results"] if (r["checks"].get("colour") or r["checks"].get("if_signed")) == "green"]
    cols = {"envelope": "#2a7", "room": "#fa0", "court": "#a6c", "lane": "#07c", "building": "#c22"}
    for r in greens[:1]:
        dr = r["checks"].get("drawing") or {}
        for k in ("envelope", "room", "court", "lane", "building"):
            v = dr.get(k)
            if not v:
                continue
            rings = v if isinstance(v[0][0], list) else [v]
            for ring in rings:
                xs, ys = zip(*ring)
                ax.plot(xs, ys, color=cols[k], lw=1.4 if k != "envelope" else 1, ls="--" if k == "envelope" else "-", label=k)
        ax.set_title(f"{d['tlid']}  {d['jurisdiction']} {d['zone']}  {d['address']}\n{r['design']} (green design)  lot {d['area_sqft']:.0f} sqft", fontsize=9)
    h, l = ax.get_legend_handles_labels()
    seen = dict(zip(l, h)); ax.legend(seen.values(), seen.keys(), fontsize=7)
    ax.set_aspect("equal"); ax.tick_params(labelsize=6)
    fig.savefig(out_png / f"{slug}.png", dpi=90); plt.close(fig)
    s = slim({k: v for k, v in d.items() if k not in ("neighbours", "geom")})
    s["lot_ring_ft_srid2913"] = [[round(a, 1), round(b, 1)] for a, b in list(lot.exterior.coords)] if lot.geom_type == "Polygon" else "multipolygon"
    s["neighbour_summary"] = [{"tlid": n["tlid"], "zone": n["zone"], "area": n["area"], "addr": n["addr"]} for n in (d["neighbours"] or [])]
    (out_txt / f"{slug}.json").write_text(json.dumps(s, indent=1, default=str))
    print(slug)
