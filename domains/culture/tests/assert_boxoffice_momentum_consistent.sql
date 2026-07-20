-- 모멘텀 파생 불변식 단언(#270): delta = prev - rank, status 부호 일치, new ⟺ 어제 부재.
--   위반 행이 하나라도 있으면 실패.
select
    snapshot_date, rank_no, performance_id,
    rank_prev_3d, rank_delta_3d, is_new_entry, momentum_status
from {{ ref('gold_culture_boxoffice_daily') }}
where
    -- delta 계산 불변식
    (rank_prev_3d is not null and rank_delta_3d is distinct from (rank_prev_3d - rank_no))
    -- rising/falling 은 delta 부호와 일치
    or (momentum_status = 'rising'  and (rank_delta_3d is null or rank_delta_3d <= 0))
    or (momentum_status = 'falling' and (rank_delta_3d is null or rank_delta_3d >= 0))
    -- new 는 어제 부재(is_new_entry)와 동치
    or (momentum_status = 'new' and is_new_entry = false)
    or (momentum_status != 'new' and is_new_entry = true)
