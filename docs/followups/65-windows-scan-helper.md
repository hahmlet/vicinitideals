# 65. The Windows PC as an idle-time scan helper (Steph 2026-10-09 asked; offered, not started).

65. [Steph] [scan: YES (a proof run: every answer must come out identical to 137's)] **The Windows PC
   as an idle-time scan helper (Steph 2026-10-09 asked; offered, not started).** Scans are
   CPU-bound (item 46: >14 processes buy nothing on 137; memory only sets how many run at
   once; disk is not a limit -- inputs ~2.5 GB). The Windows PC (i7-11700F, 8 cores / 16
   threads, 32 GB, 355 GB free) is worth ~half of 137. Shape: 137 stays the owner of every
   job; a bound is cut into lot chunks (the bridge already writes per-chunk parts and
   resumes from them); a small helper on Windows, started only when the PC is idle (no
   input for N minutes, low CPU) and stopped the moment it is used, takes chunks, sends
   parts back; a chunk not returned in time goes back to 137. Off/asleep PC = slower, never
   wrong or stuck. Needs: inputs synced to the PC once per snapshot, the same code sha,
   a proof that a chunk scored on Windows equals 137's answer (Windows vs Linux floating
   point), and a cap so the PC never runs hot while in use (item 32). ~2-4 days of agent
   work. Steph to decide; measure the 137 queue first (46(d) lockwatch on 137,
   /root/lockwatch.log, every 5 min since 2026-10-10).
