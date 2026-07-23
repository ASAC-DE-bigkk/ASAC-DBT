-- ppltn_dow_hour 불변식: grain(area_cd,dow,hr) 범위 + base_n>=1 + min<=avg<=max.
select area_cd, dow, hr
from {{ ref('gold_citydata_ppltn_dow_hour') }}
where dow < 1 or dow > 7
   or hr < 0 or hr > 23
   or base_n < 1
   or min_ppltn > avg_ppltn
   or avg_ppltn > max_ppltn
