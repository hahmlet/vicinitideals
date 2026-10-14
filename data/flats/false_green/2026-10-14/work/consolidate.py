"""Round 2: merge the eight reader CSVs, apply coordinator overrides, weight by stratum.
Same weighting and bands as round 1 (2026-10-10/work/consolidate.py); run from this folder's parent:
    cd data/flats/false_green/2026-10-14 && python work/consolidate.py
"""
import collections
import csv
import glob
import random
from math import comb

FIELDS = ["tlid", "city", "zone", "ruling", "reason", "kind", "place", "item", "policy"]

rows = []
for f in sorted(glob.glob("work/results/B[0-9].csv")):
    with open(f, newline="", encoding="utf-8") as fh:
        rows += list(csv.DictReader(fh))

strata = {}
with open("work/sample.psv", encoding="utf-8") as fh:
    for line in fh:
        line = line.rstrip("\n")
        if not line:
            continue
        j, rn, lid, tlid, zone, addr, tot = line.split("|")
        strata[tlid] = (j, int(tot))

# Coordinator overrides after checking a reader's ruling: tlid -> dict of fields to replace.
# Kinds harmonised so the two rounds count "known kind in a new place" the same way: the
# readers' rulings and reasons stand; only the kind label moves.
DEDICATION = "KNOWN-67:street land to the centre line (dedication / added setback) not taken off the fit"
OVERRIDE = {
    # Sherwood 16.106.020 A + 16.106.040 D: same mechanism as item 67, a city not seen before.
    "2S132CD12600": {"kind": DEDICATION + " (Sherwood 16.106.040 D)", "place": "new-place", "item": "67"},
    "2S132AC01500": {"kind": DEDICATION + " (Sherwood 16.106.040 D)", "place": "new-place", "item": "67"},
    "2S116AA14200": {"kind": DEDICATION + " (county 304-2.14 C in King City; KCMC 16.80.060 A twin)"},
    "31E01DA00229": {"kind": DEDICATION + " (Oregon City 16.12.011.B, Table 16.12.016)"},
    "1N223DA11500": {"kind": DEDICATION + " (county 302-2.14 C(1)(c), collector 37 ft)"},
    # TO 375-7 30.c: the Type I path ends at 10,000 sf buildable area; the rest is Type II only.
    # Type II = the Hillsboro Development Review shape Steph ruled red (item 53/69), so this is the
    # by-right kind in a new place, as Hillsboro was in round 1.
    "1S103DA00200": {
        "kind": "KNOWN-53:Type II-only path shown green (WashCo 375-7 30.c(i) 10,000 sf buildable-area gate; R-5..R-25+ have twins)",
        "place": "new-place",
        "item": "53",
    },
}

with open("work/sample.psv", encoding="utf-8") as fh:
    city_of = {ln.split("|")[3]: ln.split("|")[0] for ln in fh if ln.strip()}

out = []
for r in rows:
    r = {k: (r.get(k) or "").strip() for k in FIELDS}
    r.update(OVERRIDE.get(r["tlid"], {}))
    r["city"] = city_of.get(r["tlid"], r["city"])
    out.append(r)

n_lots = len(strata)
assert len(out) == n_lots and len({r["tlid"] for r in out}) == n_lots, (len(out), n_lots)
assert all(r["tlid"] in strata for r in out), [r["tlid"] for r in out if r["tlid"] not in strata]
assert all(r["ruling"] in ("RIGHT", "WRONG", "CANT_TELL") for r in out)

with open("false_green_round2.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=FIELDS, quoting=csv.QUOTE_ALL)
    w.writeheader()
    w.writerows(sorted(out, key=lambda r: (strata[r["tlid"]][0], r["tlid"])))

cnt = collections.Counter(r["ruling"] for r in out)
print("counts", dict(cnt))
pol = [r for r in out if r["policy"]]
print("policy lots", len(pol))
for r in pol:
    print("  ", r["tlid"], r["city"], r["zone"], r["ruling"], "|", r["policy"])
for r in out:
    if r["ruling"] != "RIGHT":
        print(r["ruling"], r["tlid"], r["city"], r["zone"], r["kind"], r["place"], r["item"], "|", r["reason"][:160])

by = collections.defaultdict(lambda: [0, 0, 0, 0])  # n, wrong, cant, N
for r in out:
    j, tot = strata[r["tlid"]]
    s = by[j]
    s[0] += 1
    s[3] = tot
    if r["ruling"] == "WRONG":
        s[1] += 1
    if r["ruling"] == "CANT_TELL":
        s[2] += 1
N = sum(s[3] for s in by.values())
print("strata", len(by), "green total", N)
for j, s in sorted(by.items(), key=lambda x: -x[1][3]):
    print(f"{j:40s} n={s[0]:3d} wrong={s[1]} cant={s[2]} N={s[3]} weight={s[3] / N:.4f}")


def point(idx):
    return sum(s[3] / N * s[idx] / s[0] for s in by.values())


print("weighted wrong", point(1), "weighted wrong+cant", point(1) + point(2))
print("lots implied", round(point(1) * N), round((point(1) + point(2)) * N))

random.seed(20261014)


def sim(extra):
    vals = []
    for _ in range(20000):
        t = 0
        for s in by.values():
            x = s[1] + (s[2] if extra else 0)
            p = random.betavariate(x + 0.5, s[0] - x + 0.5)
            t += s[3] / N * p
        vals.append(t)
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[int(0.5 * len(vals))], vals[int(0.975 * len(vals))]


print("band wrong (Jeffreys per stratum)", sim(False))
print("band wrong+cant", sim(True))
n = len(out)
x = cnt["WRONG"]
print("raw", x, n, x / n)


def cdf(k, n, p):
    return sum(comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))


def bis(f, lo, hi):
    for _ in range(80):
        m = (lo + hi) / 2
        if f(m) > 0:
            lo = m
        else:
            hi = m
    return lo


lo = bis(lambda p: 0.025 - (1 - cdf(x - 1, n, p)), 0.0, 0.5) if x else 0.0
hi = bis(lambda p: cdf(x, n, p) - 0.025, 0.0, 0.5)
print("CP unweighted", lo, hi)


def kish_cp(strata_counts):
    """Weighted rate with a 95% Clopper-Pearson band on the Kish effective sample size.
    strata_counts: {stratum: (n, wrong, N)}. Each lot carries weight N/n."""
    Nt = sum(N for n, x, N in strata_counts.values())
    p = sum(N / Nt * x / n for n, x, N in strata_counts.values())
    w = [N / n for n, x, N in strata_counts.values() for _ in range(n)]
    n_eff = sum(w) ** 2 / sum(v * v for v in w)
    ne = max(1, round(n_eff))
    xe = p * ne
    lo_ = 0.0 if xe <= 0 else bis(lambda q: 0.025 - (1 - cdf(max(0, round(xe)) - 1, ne, q)), 0.0, 0.9)
    hi_ = bis(lambda q: cdf(round(xe), ne, q) - 0.025, 0.0, 0.9)
    return p, n_eff, lo_, hi_


r2 = {j: (s[0], s[1], s[3]) for j, s in by.items()}
r2c = {j: (s[0], s[1] + s[2], s[3]) for j, s in by.items()}
print("ROUND 2 kish-CP wrong      p=%.4f n_eff=%.1f band %.4f-%.4f" % kish_cp(r2))
print("ROUND 2 kish-CP wrong+cant p=%.4f n_eff=%.1f band %.4f-%.4f" % kish_cp(r2c))

# Round 1 recomputed the same way from its committed files, so the two bands compare.
r1s = {}
with open("../2026-10-10/work/sample.psv", encoding="utf-8") as fh:
    for line in fh:
        if line.strip():
            j, rn, lid, tlid, zone, addr, tot = line.rstrip("\n").split("|")
            r1s[tlid] = (j, int(tot))
r1 = collections.defaultdict(lambda: [0, 0, 0])
with open("../2026-10-10/false_green_round1.csv", newline="", encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        j, tot = r1s[row["tlid"]]
        r1[j][0] += 1
        r1[j][1] += row["ruling"] == "WRONG"
        r1[j][2] = tot
print("ROUND 1 kish-CP wrong      p=%.4f n_eff=%.1f band %.4f-%.4f" % kish_cp({j: tuple(v) for j, v in r1.items()}))

# Share of greens by wrong kind (weighted).
kinds = collections.defaultdict(float)
for r in out:
    if r["ruling"] == "WRONG":
        j, tot = strata[r["tlid"]]
        kinds[r["kind"].split(":")[0] + ":" + r["kind"].split(":")[1].split(" (")[0]] += tot / N / by[j][0]
for k, v in sorted(kinds.items(), key=lambda x: -x[1]):
    print(f"kind share {v:.4f} ~{round(v * N)} lots  {k}")

# Weighted rate excluding the strata new since round 1, to compare like with like.
new = {"or/washington/tigard", "or/washington/cornelius", "or/clackamas/estacada"}
old = {j: s for j, s in by.items() if j not in new}
No = sum(s[3] for s in old.values())
print("weighted wrong, round-1 places only", sum(s[3] / No * s[1] / s[0] for s in old.values()))

# Both rounds pooled on run 74's stratum totals. Round 1's Hillsboro lots are left out: their
# zones went red in run 73 (item 69), so they no longer belong to the green population.
pool = collections.defaultdict(lambda: [0, 0, 0])
for j, (n, x, Nn) in r2.items():
    pool[j][0] += n
    pool[j][1] += x
    pool[j][2] = Nn
for j, (n, x, Nn) in r1.items():
    if j == "or/washington/hillsboro" or j not in pool:
        continue
    pool[j][0] += n
    pool[j][1] += x
print("POOLED kish-CP wrong p=%.4f n_eff=%.1f band %.4f-%.4f" % kish_cp({j: tuple(v) for j, v in pool.items()}),
      "lots", sum(v[0] for v in pool.values()), "wrong", sum(v[1] for v in pool.values()))
