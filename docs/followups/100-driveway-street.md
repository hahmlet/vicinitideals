# 100. Driveway street: measure it instead of asking (follow-on of 88/89).

100. [Claude] [scan: YES (yellows only go green)] **Driveway street: measure it instead of asking** -- MERGED e63617b8, LIVE (run 124). A driveway too wide for the frontage cap on the lot's shortest street but fine on a longer one is YELLOW (MEASURE-DRIVE-STREET), not red -- the screen does not draw which street the drive uses.
   OPEN, two ways to turn these yellows into answers: (a) measure the street line the drawn drive crosses (as `parking_frontage` does for the court); (b) a Happy Valley street-class map, so 16.44's lowest-class corner rule can pick the street (corner lots stay yellow on ACCESS-STREET-RANK-UNKNOWN until then).
