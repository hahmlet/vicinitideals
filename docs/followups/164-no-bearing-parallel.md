# 164. Turned pod not held back where no street direction was measured

From tigard-entrances (d35ef11a). In zones needing the long side parallel to the street, a lot with no measured street direction let a turned pod through (possible false GREEN).

**Status 2026-11-13:** BUILT on flats/no-bearing (9f8f71dd, 32a510bf: hold on MEASURE-STREET-DIRECTION where a street line has no bearing; a lot with no street line at all keeps today's RED). Merged into flats/rel8 as 1adb4acd; rides rel8 (bound running 11-13). The side-door guard 23cf2ca7 is already on main as 6f738aed.
