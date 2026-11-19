# 207 Public data candidates (Steph links, 2026-11-18)

Steph sent ten public data links; scouted the same day (nothing downloaded). Most duplicate what FLATS holds (3DEP, SLIDO 4.5, SSURGO hydric). Two candidates, neither started:

1. **Surface geology for the foundation agent (use B).** USGS SIM-3443 Portland map (2020, 1:63,360, 47 MB gdb, pubs.usgs.gov/sim/3443/database/sim3443_gdb.zip); DOGAMI OGDC-8 compilation (119 MB, pubs.oregon.gov/dogami/dds/p-OGDC-8); DOGAMI O-13-12 Portland 3D geology (possible fill / depth-to-bedrock; not opened). Regional scale: a hint per lot, not a finding. Unconfirmed: whether SIM-3443 maps artificial fill. Links were given to the foundation agent in fd5-pass2-summary.md to evaluate itself (Steph: "let them figure it out"); only build a per-lot join if they ask.
2. **Federal stream map as a flag (use A).** NHDPlus HR Willamette (NHDPLUS_H_1709_HU4_GDB.zip, 397 MB, prd-tnm.s3.amazonaws.com StagedProducts/Hydrography). ~1:24,000, no buffer rule, so a YELLOW flag only, where a city has no stream layer (Canby, Sandy, Washington County cities -- first check whether they have their own). After rel11.

Not worth it: BLM PLSS (survey grid, not ownership), NLCD (30 m), SoilWeb (point lookup only), Oregon Wetland Soils (same hydric ratings we hold).
Oregon gNATSGO 2024 (515 MB, ftp.gis.oregon.gov/framework/geoscience/Soils_framework_data/gNATSGO_OR2024.zip): Steph 11-18 "If the Oregon gNATSGO is complete, then I don't see any reason to not treat it as an authoritative source"; USGS conflicts sorted later.
