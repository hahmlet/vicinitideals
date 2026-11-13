# 190. Grow the analysis machine's (LXC 137) disk -- blocked on the shared drive being full

**Status:** WAITING ON STEPH (2026-11-12). Steph asked: "next time you're in between scans,
go ahead and bump the size of the storage on the machine."

**Why not done yet:** LXC 137's disk is a quota on the Proxmox host's fast pool `rpool`,
which is shared with production VM 114. Checked 2026-11-12:

- `rpool` 1.81T, 95% full, 80 GB raw free; every dataset shows only **23 GB available**.
- 137: refquota 80G, 15.3G free inside it, but the dataset USES 160G -- **95.7G is held by
  zfs-auto-snapshot snapshots** (deleted bundles stay on the pool until their snapshots expire;
  biggest: daily-2026-11-06 12.1G, weekly-2026-10-04 6.25G).
- Raising 137's quota without freeing pool space would let a bound fill the pool and take
  production down with it.

**Dry-run reclaim (`zfs destroy -nv`):** 137 snapshots older than 11-01 -> 56.1G;
older than 11-08 -> 90.6G; all -> 95.7G.

**Proposed (needs Steph's yes -- snapshot deletion is permanent):**
1. Between scans, destroy 137 snapshots older than one week (~90 GB back to the pool).
2. `pct resize 137 rootfs 120G` (grow-only, online, instant on ZFS).
3. Optional standing change: `zfs set com.sun:auto-snapshot=false` on 137 (its data is
   regenerable and churns tens of GB per bound), or keep dailies only.

Run from LXC 112: `ssh proxmox-host "..."`. Wider pool pressure (var-lib-vz 1.04T with 360G
of snapshots, vm-114 220G of snapshots) is the personalproxmox lane, not FLATS.
