# 147. The maximum front setback was never checked on its own -- FALSE GREEN RISK (found 2026-11-04)

[Claude] [scan: YES -- toward red]

DONE and live (run 124): the max-front check, each-named-street reading, South Hillsboro active streets + centre cores, the slide/snap fix-forward
(20fbf9ed, 586a7b9b, 33911e99, 8adfedd5, e2f5546d, 513d27bf; rel3 read SHIP 11-08, rel4 shipped the fix-forward). The three Tigard RES-B lots
(2S103BA00137, 2S103DD00434, 2S103BA00108) were re-read in rel4-fixes and stay RED honestly.

STILL OPEN (Claude, no Steph answer; conservative direction, not a false green):
- 2026-11-13 CLOSED (small-fixes-9, no code change): Portland CM2 1S2E17BA  -14300 (7111 SE Foster Rd) is a TRUE RED on run 124. Corner lot on two streets (SE Foster, SE 71st), so 33.130.215.C.2.c holds the 10 ft maximum on both. The drawn pod stands 5.2 ft from Foster but 18.0 ft (17.3 after the strip) from 71st at its nearest point, so even the lenient reading misses. The fit has 1 ft of slack: the room (pod + rear court, 80 x 73 ft) is pinned by the north line and the Foster diagonal and cannot move west; turned it does not fit; court toward Foster puts the building 43+ ft off Foster. The 16.52 ft / 5.0 / 8.5 ft figures came from an earlier drawing.
- Not encoded on purpose (conservative, unset): Portland EX Standard 2 and CI2/IR "within 100 ft"; King City, Gladstone C2, Oregon City MUC-2 maximum.
