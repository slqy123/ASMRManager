select count(*) 'c', t.name
from asmr
         join asmrs2tags a2t on asmr.id = a2t.asmr_id
         join tag t on a2t.tag_id = t.id
         join asmrs2vas a2v on asmr.id = a2v.asmr_id
         join voice_actor va on a2v.actor_id = va.id
where true
group by t.name
order by c desc;

select distinct asmr.id
from asmr
         join asmrs2tags a2t on asmr.id = a2t.asmr_id
         join tag t on a2t.tag_id = t.id
         join asmrs2vas a2v on asmr.id = a2v.asmr_id
         join voice_actor va on a2v.actor_id = va.id
where true
  and t.name='tag.name'
group by asmr.id
order by dl_count * price desc
