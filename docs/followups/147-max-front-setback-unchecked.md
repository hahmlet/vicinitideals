# 147. The maximum front setback was never checked on its own -- FALSE GREEN RISK (found 2026-11-04)

[Claude] [scan: YES -- toward red]

DONE and live (run 124): the max-front check, each-named-street reading, South Hillsboro active streets + centre cores, the slide/snap fix-forward
(20fbf9ed, 586a7b9b, 33911e99, 8adfedd5, e2f5546d, 513d27bf; rel3 read SHIP 11-08, rel4 shipped the fix-forward). The three Tigard RES-B lots
(2S103BA00137, 2S103DD00434, 2S103BA00108) were re-read in rel4-fixes and stay RED honestly.

STILL OPEN (Claude, no Steph answer; conservative direction, not a false green):
- Possible wrong RED: Portland CM2 `1S2E17BA  -14300` reads 16.52 ft over a 10 ft maximum, but both street lines are 5.0 and 8.5 ft from
  the building's nearest point -- may be the facade-share measure. Never re-checked (rel3.moveread.md item 2). Check, fix forward if wrong.
- Not encoded on purpose (conservative, unset): Portland EX Standard 2 and CI2/IR "within 100 ft"; King City, Gladstone C2, Oregon City MUC-2 maximum.
