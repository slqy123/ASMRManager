select asmr.id,title,circle_name,nsfw,release_date,price,dl_count,star,asmr.count,held,has_subtitle, va.name
from asmr
         join asmrs2tags a2t on asmr.id = a2t.asmr_id
         join tag t on a2t.tag_id = t.id
         join asmrs2vas a2v on asmr.id = a2v.asmr_id
         join voice_actor va on a2v.actor_id = va.id
where true
and asmr.star = 5
and held = false
group by asmr.id
order by dl_count * price desc
limit 20;

