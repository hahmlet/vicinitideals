"""Merge the eight reader CSVs, apply coordinator overrides, weight by stratum."""
import csv, glob, random, collections

rows = []
for f in sorted(glob.glob("work/results/A[0-9].csv")):
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

OVERRIDE = {
    "1S2E02BB  -01100": (
        "RIGHT",
        "CE 6.66-acre lot with a 75,050 sf operating commercial building (closed single-tenant Fabric Depot big box, not a multi-tenant centre, so not Steph's malls-red ruling); every CE standard FLATS holds passes (FAR 0.014 vs 2.5, landscaped 98.8%). POLICY: operating building ignored (pod dropped in the lot corner, probably on its parking).",
    ),
}
out = []
for r in rows:
    if r["tlid"] in OVERRIDE:
        r["ruling"], r["reason"] = OVERRIDE[r["tlid"]]
        r["kind"] = ""
    out.append(r)

assert len(out) == 102 and len({r["tlid"] for r in out}) == 102
assert all(r["tlid"] in strata for r in out), [r["tlid"] for r in out if r["tlid"] not in strata]

with open("false_green_round1.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["tlid", "city", "zone", "ruling", "reason", "kind"], quoting=csv.QUOTE_ALL)
    w.writeheader()
    w.writerows(out)

cnt = collections.Counter(r["ruling"] for r in out)
print("counts", dict(cnt))
pol = [r for r in out if "POLICY" in r["reason"]]
print("policy lots", len(pol))
for r in pol: print("  ", r["tlid"], r["city"], r["zone"])

by = collections.defaultdict(lambda: [0, 0, 0, 0])  # n, wrong, cant, N
for r in out:
    j, tot = strata[r["tlid"]]
    s = by[j]; s[0] += 1; s[3] = tot
    if r["ruling"] == "WRONG": s[1] += 1
    if r["ruling"] == "CANT_TELL": s[2] += 1
N = sum(s[3] for s in by.values())
print("strata", len(by), "green total", N)
for j, s in sorted(by.items(), key=lambda x: -x[1][3]):
    print(f"{j:40s} n={s[0]:3d} wrong={s[1]} cant={s[2]} N={s[3]}")

def point(idx):
    return sum(s[3] / N * s[idx] / s[0] for s in by.values())
print("weighted wrong", point(1), "weighted wrong+cant", point(1) + point(2))

random.seed(20261010)
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
    return vals[int(.025 * len(vals))], vals[int(.5 * len(vals))], vals[int(.975 * len(vals))]
print("band wrong", sim(False))
print("band wrong+cant", sim(True))
# unweighted
n = len(out); x = cnt["WRONG"]
print("raw", x, n, x / n)

# bootstrap of the weighted rate (resample lots within each stratum)
random.seed(7)
bs = []
for _ in range(20000):
    t = 0
    for s in by.values():
        k = sum(1 for _ in range(s[0]) if random.random() < s[1] / s[0])
        t += s[3] / N * k / s[0]
    bs.append(t)
bs.sort()
print("bootstrap", bs[int(.025 * len(bs))], bs[int(.975 * len(bs))])
# exact (Clopper-Pearson) via bisection on the binomial tail, 4 of 102
from math import comb
def cdf(k, n, p): return sum(comb(n, i) * p**i * (1 - p)**(n - i) for i in range(k + 1))
def bis(f, lo, hi):
    for _ in range(80):
        m = (lo + hi) / 2
        if f(m) > 0: lo = m
        else: hi = m
    return lo
n, x = 102, 4
print("CP lower", bis(lambda p: 0.975 - (1 - cdf(x - 1, n, p)) if False else (1 - cdf(x - 1, n, p)) - 0.025, 0, 0.5) if False else None)
lo = bis(lambda p: 0.025 - (1 - cdf(x - 1, n, p)), 0.0, 0.5)
hi = bis(lambda p: cdf(x, n, p) - 0.025, 0.0, 0.5)
print("CP", lo, hi)
n_pol = 17
print("policy share of sample", n_pol / 102)
