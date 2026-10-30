# 46. Scans (bounds) on 137 are the lanes' bottleneck (Steph 2026-10-06: ~1 h coding, then 5-6 h waiting for one scan at a time; four lanes queue on `heavy.lock`).

46. [Claude] [Steph: (d) after the measuring, (f) after the re-measure] [scan: YES (a proof run: every answer must come out identical)] **Scans (bounds) on 137 are the lanes' bottleneck (Steph 2026-10-06:
   ~1 h coding, then 5-6 h waiting for one scan at a time; four lanes
   queue on `heavy.lock`).** (a)-(c) SHIPPED 24a61695 2026-10-08
   (`flats/ingest/batch.py`: costliest lots first, memory-booked chunks, a
   dead worker costs one lot, `--cache`; proof 4 SAME on every run). 137 is
   now CPU-bound, so more than 14 processes buys nothing. (e) fewer lanes:
   not pursued. (g) GPU: Steph 2026-10-07 dropped it ("forget those two
   questions").
   (d) rented compute -- PARKED by Steph 2026-10-08 ("won't do for now";
   keep the research, don't delete it). 2026-10-09 RE-ASKED (Steph moving to
   Max 20x and 7-9 parallel agents; the Proxmox host is maxed -- 137 already
   has 16 of the i5-14600KF's 20 threads, so no free home capacity): est.
   at 7-9 agents ~3,000-4,000 vCPU-h/month beyond 137 = ~$250-350/month.
   Steph: NOT YET, MEASURE FIRST -- run a week at 7-9 agents, log how long
   checks wait on heavy.lock per day, decide with that number. Steph
   2026-10-06 PREFERS CLOUDFLARE (a commercial version would run there):
   Cloudflare Containers (GA 2026-04-13), many small boxes of at most 4 vCPU /
   12 GiB / 20 GB each, up to 1,500 vCPU per account at once; CPU billed
   only while busy ($0.072/vCPU-h), memory while running
   ($0.009/GiB-h), so ~$0.40 per busy 4-vCPU box-hour; inputs via an
   R2 bucket mounted in the box; $5/month Workers Paid plan. Est. (to
   prove on a first trial): full re-screen under an hour for ~$10-20, a
   lane bound ~10-15 min for ~$1-3, a 2,000-lot sample ~$0.30. Build:
   a chunk mode for the bridge, a dispatcher Worker + Durable Object,
   answers written as `AnswerCache` files to R2 and merged by the
   existing cache read; first rented run must reproduce a 137 run
   exactly. Risk: a lot that needs more than ~11 GB cannot run in a
   12 GiB box -- those stay on 137; the first full run's
   `timings.parquet` (peak memory per lot) counts them. Steph's part:
   Workers Paid plan, an API token (Containers, Workers, R2) in a file
   outside the repo, a monthly budget alert. Fallback considered:
   Hetzner CCX63 in Hillsboro OR (48 vCPU / 192 GB, ~$1.64/h, billed
   until DELETED; one big machine, least build).
   (f) skip big PRIVATE lots by size -- Steph 2026-10-06 DEFERRED: "see what
   the institutional changes remove" (item 47), then decide. Item 47 has
   landed (ca06c2ff; scans skip institutional land c1a96d81), so this is
   now ready to re-measure with a full
   run's `timings.parquet` and bring to Steph. Measured before 47 on
   quadfit_2026-10-01_wash (418,021 lots screened): 861 lots >= 10 ac (660
   10-20, 167 20-44, 34 >= 44; biggest 194.8 ac 1S1080000504) = ~11% of the
   cost proxy; 47's signals (Washington PUB or PROP_CODE 9xx: 90; Multnomah
   ASSESSVAL 0 with TOTALVAL > 0: 109) leave ~660, mostly private (vacant,
   MFR, COM, farm, SFR acreage; Clackamas's 181 unsorted).
