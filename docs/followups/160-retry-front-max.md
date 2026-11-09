# 160. Placement retry never checks the maximum front setback

fire-reds-158 built and withdrew two retry changes: the placement retry never checks the maximum
front setback, so a retried placement can sit further back than the code allows. The gap exists
on main today -> possible false GREEN. Withdrawn change sent 1S2E07BC -12600 (Portland) to a wrong RED.
Lane: flats/retry-front-max stacked on flats/fire-reds-158; must measure how many current GREENs rely
on a retried placement that breaks a front maximum. Hand-off ../vicinitideals-worktrees/retry-front-max.handoff.md.
