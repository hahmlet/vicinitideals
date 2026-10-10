-- Seed string: fgs-2026-10-10-seed1 ; a lot is GREEN if ANY design's colour (checks.colour, else if_signed) is green in run 70.
with g as (
  select r.lot_id from flats.lot_results r where r.run_id = 70
  group by r.lot_id
  having bool_or(coalesce(r.checks->>'colour', r.checks->>'if_signed') = 'green')
), tot as (
  select l.jurisdiction, count(*) n from flats.lots l join g on g.lot_id = l.id group by 1
), ranked as (
  select l.id, l.tlid, l.jurisdiction, l.zone, l.site_address,
         row_number() over (partition by l.jurisdiction order by md5(l.tlid || 'fgs-2026-10-10-seed1')) rn
  from flats.lots l join g on g.lot_id = l.id
)
select ranked.jurisdiction, ranked.rn, ranked.id, ranked.tlid, ranked.zone, ranked.site_address, tot.n
from ranked join tot using (jurisdiction)
where rn <= case ranked.jurisdiction
  when 'or/multnomah/portland' then 38
  when 'or/washington/_unincorporated' then 11
  when 'or/clackamas/_unincorporated' then 7
  when 'or/washington/beaverton' then 4
  when 'or/clackamas/oregon-city' then 3
  when 'or/multnomah/gresham' then 3
  else 3 end
order by ranked.jurisdiction, rn;
