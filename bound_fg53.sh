#!/bin/bash
# FOLLOWUPS 53 bound (A): quadfit measures the lots of Canby, Sandy and Estacada.
# s1->s7 into a COPY tree of the 10-07 weekly; then bound (no existing lot may change).
cd /root/code/fg53
export PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 PYTHONPATH=/root/code/fg53
PY=/root/code/vicinitideals/.venv/bin/python
D=/root/code/vicinitideals/data
Q0=$D/quadfit_2026-10-07_weekly
Q=$D/quadfit_2026-10-07_fg53
echo "=== start $(date -u)"; git log --oneline -1
mkdir -p $Q/raw
for f in $Q0/raw/*; do b=$(basename $f); [ -e $Q/raw/$b ] || ln -s $(readlink -f $f) $Q/raw/$b; done
for c in canby sandy estacada; do [ -e $Q/raw/zoning_$c.geojson ] || cp $Q0/raw/zoning_gladstone.geojson $Q/raw/zoning_$c.geojson; done
cp $Q0/funnel.json $Q/ 2>/dev/null
QUADFIT_DATA_DIR=$Q $PY "Lot Analysis/quadfit/run_all.py" --stage s1 --force > /root/quadfit_fg53.log 2>&1
echo "QUADFIT EXIT $? $(date -u)"; tail -3 /root/quadfit_fg53.log
[ -f $Q/lots_results.csv ] || { echo NO QUADFIT RESULTS; exit 1; }
$PY /root/bound_mhq.py $Q0 $Q /root/fg53_scope.txt > /root/bound_fg53.log 2>&1
echo "BOUND EXIT $? $(date -u)"; cat /root/bound_fg53.log
echo "CHAIN_FG53_A DONE $(date -u)"
