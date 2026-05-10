# 2025 Portland-Vancouver-Hillsboro MSA AMI rent and income limits.
# Source: Portland Housing Bureau 2025 Income and Rent Limits (PHB).
# Base 4-person AMI = $124,100.

AMI_RENT_LIMITS = {
    30:  {0: 585,  1: 682,  2: 820,  3: 947,  4: 1075},
    50:  {0: 973,  1: 1136, 2: 1364, 3: 1576, 4: 1789},
    60:  {0: 1168, 1: 1362, 2: 1637, 3: 1891, 4: 2146},
    80:  {0: 1558, 1: 1817, 2: 2186, 3: 2530, 4: 2866},
    100: {0: 1738, 1: 1862, 2: 2235, 3: 2530, 4: 3217},
    120: {0: 1870, 1: 2234, 2: 2682, 3: 3036, 4: 3860},
}

# Keyed by (ami_pct, household_size_persons). Standard HUD sizing per BR count.
AMI_INCOME_LIMITS = {
    30:  {1: 26100,  2: 29800,  3: 33550,  4: 37250,  5: 40250},
    50:  {1: 38950,  2: 45450,  3: 51950,  4: 58450,  5: 64900},
    60:  {1: 46750,  2: 54500,  3: 62350,  4: 70150,  5: 77900},
    80:  {1: 69550,  2: 79550,  3: 89400,  4: 99300,  5: 107250},
    100: {1: 86870,  2: 99280,  3: 111690, 4: 124100, 5: 134028},
    120: {1: 104244, 2: 119140, 3: 134038, 4: 148920, 5: 160834},
}

# HUD-standard household size per bedroom count (used for income limit lookup).
_HH_SIZE = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5}

AMI_TIERS = [30, 50, 60, 80, 100, 120]


def get_ami_tier(beds: int, monthly_rent: float) -> dict:
    """Return the lowest AMI tier whose rent limit >= monthly_rent for the given bedroom count."""
    beds = min(max(int(beds), 0), 4)
    for tier in AMI_TIERS:
        limit = AMI_RENT_LIMITS[tier][beds]
        if monthly_rent <= limit:
            hh = _HH_SIZE[beds]
            return {
                "ami_pct": tier,
                "rent_limit": limit,
                "income_limit": AMI_INCOME_LIMITS[tier].get(hh),
            }
    return {"ami_pct": None, "rent_limit": None, "income_limit": None}
