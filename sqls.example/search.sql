select asmr.id,title,circle_name,nsfw,release_date,price,dl_count,star,asmr.count,held,has_subtitle, va.name
from asmr
         join asmrs2tags a2t on asmr.id = a2t.asmr_id
         join tag t on a2t.tag_id = t.id
         join asmrs2vas a2v on asmr.id = a2v.asmr_id
         join voice_actor va on a2v.actor_id = va.id
where true
    and has_subtitle = true
    and asmr.count = 0
    -- and t.name = 'tag.name'
    -- and tag_id = tag.id
    and nsfw = false
--     and t.cn_name like ''
--     and title like '%'
--   and circle_name = ''
    -- and va.name = ''
  and held = false
  and asmr.id not in (select asmr.id
                  from asmr
                           join asmrs2tags a2t on asmr.id = a2t.asmr_id
                           join tag t on a2t.tag_id = t.id
                           join asmrs2vas a2v on asmr.id = a2v.asmr_id
                           join voice_actor va on a2v.actor_id = va.id
                  where t.name = 'tag.name'
                  group by asmr.id)
group by asmr.id
order by dl_count * price * random() desc
limit 20;
