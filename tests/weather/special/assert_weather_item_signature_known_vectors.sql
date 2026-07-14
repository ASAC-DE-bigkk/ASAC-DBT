with vectors (
    base_date,
    base_time,
    nx,
    ny,
    category,
    fcst_date,
    fcst_time,
    fcst_value,
    expected_hash
) as (
    values
        (
            '20260712', '0500', '060', '127', ' tmp ', '20260712', '0600', '1.5',
            '4d7ae418621bf4bb7ecb7e551b7b626a8415d161362baab661ebb424c45dc197'
        ),
        (
            cast(null as varchar), cast(null as varchar), cast(null as varchar), cast(null as varchar),
            cast(null as varchar), cast(null as varchar), cast(null as varchar), cast(null as varchar),
            '129834ce8c6e874985eee88f256855ddde25b8c45bc498a8414aaf063baa2c9f'
        )
),
calculated as (
    select
        expected_hash,
        {{ weather_kma_item_signature(
            'base_date', 'base_time', 'nx', 'ny', 'category',
            'fcst_date', 'fcst_time', 'fcst_value'
        ) }} as actual_hash
    from vectors
)
select *
from calculated
where actual_hash is distinct from expected_hash
