with allowed_duplicates(alias_name) as (
    values
        ('신사동')
),

mapping_aliases as (
    select
        trim(alias_name) as alias_name,
        place_id
    from {{ ref('weather_place_grid_mapping') }}
    cross join unnest(split(alias_names, '|')) as alias(alias_name)
    where trim(alias_name) <> ''
),

duplicates as (
    select
        alias_name,
        count(distinct place_id) as place_count
    from mapping_aliases
    group by alias_name
    having count(distinct place_id) > 1
)

select duplicates.*
from duplicates
left join allowed_duplicates
    on duplicates.alias_name = allowed_duplicates.alias_name
where allowed_duplicates.alias_name is null
