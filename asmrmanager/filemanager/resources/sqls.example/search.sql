-- 作品筛选
-- 如果你不清楚具体的tag名，声优，社团名，虽然可以用sql搜索，
-- 但更方便的方法其实是用类似db browser for sqlite, usql, litecli,之类的数据库工具直接去看项目根目录下的data.db，或者直接去网站看
select asmr.id,title,circle_name,nsfw,release_date,price,dl_count,star,asmr.count,held,has_subtitle, va.name
from asmr
         join asmrs2tags a2t on asmr.id = a2t.asmr_id
         join tag t on a2t.tag_id = t.id
         join asmrs2vas a2v on asmr.id = a2v.asmr_id
         join voice_actor va on a2v.actor_id = va.id
where true
    and has_subtitle = true  -- 是否有中文字幕
    and asmr.count = 0  -- 作品review的次数
    and stored = false  -- 作品是否处于storage path
    -- and t.name = 'tag.name'  
    -- and tag_id = tag.id  -- tag id
    and nsfw = false  -- 是否为工作不宜作品
    -- and title like '%'  -- 作品标题
    -- and circle_name = ''  -- 作品所属社团名
    -- and va.name = ''  -- 声优名
  and held = false
  and asmr.id not in (select asmr.id
                  from asmr
                           join asmrs2tags a2t on asmr.id = a2t.asmr_id
                           join tag t on a2t.tag_id = t.id
                           join asmrs2vas a2v on asmr.id = a2v.asmr_id
                           join voice_actor va on a2v.actor_id = va.id
                  where t.name in ('tag.name1', 'tag.name2')  -- 过滤掉其中含有这些标签的结果
                  group by asmr.id)
group by asmr.id
order by dl_count * log(price+1)  desc  -- 排序，这里是按照下载量*价格的对数 的方式排序
limit 20;
