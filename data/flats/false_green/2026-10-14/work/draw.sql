-- Round 2 (FOLLOWUPS 64). Seed string: fgs-2026-10-14-seed2 ; a lot is GREEN if ANY design's colour
-- (checks.colour, else if_signed) is green in run 74 (live 2026-10-14). Same method as round 1
-- (2026-10-10/work/draw.sql): lots ranked by md5(tlid || seed) within each jurisdiction.
-- Oversampled vs share: Tigard, Cornelius, Estacada (new since round 1), Hillsboro and
-- Washington County unincorporated (round 1's four wrongs). Weighted back by stratum totals.
with g as (
  select r.lot_id from flats.lot_results r where r.run_id = 74
  group by r.lot_id
  having bool_or(coalesce(r.checks->>'colour', r.checks->>'if_signed') = 'green')
), tot as (
  select l.jurisdiction, count(*) n from flats.lots l join g on g.lot_id = l.id group by 1
), ranked as (
  select l.id, l.tlid, l.jurisdiction, l.zone, l.site_address,
         row_number() over (partition by l.jurisdiction order by md5(l.tlid || 'fgs-2026-10-14-seed2')) rn
  from flats.lots l join g on g.lot_id = l.id
)
select ranked.jurisdiction, ranked.rn, ranked.id, ranked.tlid, ranked.zone, ranked.site_address, tot.n
from ranked join tot using (jurisdiction)
where rn <= case ranked.jurisdiction
  when 'or/multnomah/portland' then 30
  when 'or/washington/_unincorporated' then 15
  when 'or/washington/tigard' then 8
  when 'or/clackamas/_unincorporated' then 6
  when 'or/washington/cornelius' then 6
  when 'or/washington/hillsboro' then 6
  when 'or/washington/beaverton' then 4
  when 'or/clackamas/estacada' then 4
  when 'or/clackamas/oregon-city' then 3
  when 'or/multnomah/gresham' then 3
  else 2 end
order by ranked.jurisdiction, rn;
