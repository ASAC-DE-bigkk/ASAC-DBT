with expected(alias_name) as (
    values
        ('홍대'),
        ('홍대입구'),
        ('홍대입구역'),
        ('건대'),
        ('건대입구'),
        ('건대입구역'),
        ('강남'),
        ('강남역'),
        ('성수'),
        ('성수동'),
        ('여의도'),
        ('서울역'),
        ('시청'),
        ('서울시청'),
        ('시청역'),
        ('종각'),
        ('종각역'),
        ('잠실'),
        ('잠실역'),
        ('이태원'),
        ('이태원역'),
        ('용산'),
        ('용산역'),
        ('신촌'),
        ('신촌역'),
        ('가로수길'),
        ('고속터미널'),
        ('고속터미널역'),
        ('DDP'),
        ('동대문디자인플라자'),
        ('코엑스'),
        ('삼성역')
),

mapping_aliases as (
    select
        place_id,
        trim(alias_name) as alias_name
    from {{ ref('weather_place_grid_mapping') }}
    cross join unnest(split(alias_names, '|')) as alias(alias_name)
)

select expected.alias_name
from expected
left join mapping_aliases
    on expected.alias_name = mapping_aliases.alias_name
where mapping_aliases.place_id is null
