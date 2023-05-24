-- 搜索tags
select t.name
from asmr
         join asmrs2tags a2t on asmr.id = a2t.asmr_id
         join tag t on a2t.tag_id = t.id
where asmr.id = 387655;

select *
from tag
where tag.name == 'tag.name';

