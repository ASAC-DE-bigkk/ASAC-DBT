{#
  증분 silver post-hook 디둡 매크로.

  R2 delete+insert 는 비원자적이라, **연속 두 run 이 같은 그레인(예: event_at)을 처리**할 때
  (관측시각이 여러 5분 수집 사이클에 반복 등장) 뒤 run 의 DELETE 가 앞 run 의 INSERT 를 못 봐
  (가시성 지연) 이중삽입될 수 있다. 관측이 넘어가면 그 그레인이 소스에서 사라져 룩백 self-heal
  도 불가 → 동결 중복. 이 매크로를 post_hook 으로 걸면 **매 run 끝에 출력 테이블(브론즈 스캔
  없음)** 을 그레인당 최신 order_col 1행으로 self-replace 해 항상 무중복 수렴(동결 중복도 청소).

  table+replace(전체 재빌드)는 브론즈 전체 스캔이라 느려 불가 → 출력 레이어만 싸게 디둡.
  ⚠ 소스 타임스탬프(event_at/observed_at)는 모두 여러 수집 사이클에 반복 등장하므로 **전
  증분 silver 가 B 에 취약**하다(sbike observed_at 도 중복 확인됨). 6개 전부 이 훅을 건다.
  collected_at 이 없는 silver 는 order_col 로 그레인 내 상수(observed_at)를 넘겨 distinct 로
  동일행을 제거한다(이중삽입은 동일 배치라 동일행).

  구현: 그레인별 max(order_col) 로 최신 행만 남기고(다른 collected_at 중복 제거) `distinct t.*`
  로 동일행 중복까지 collapse. **컬럼 목록/ adapter 조회 없이** t.* 로 스키마를 그대로 보존해
  parse 시점에 완전히 렌더된다(execute 가드·드리프트 커플링 없음).

  usage (모델 config):
    post_hook=dedup_latest(['area_cd', 'event_at'])
    post_hook=dedup_latest(['area_cd', 'event_at'], order_col='collected_at')
#}
{% macro dedup_latest(grain_cols, order_col='collected_at') %}
create or replace table {{ this }} as
with _latest as (
    select {{ grain_cols | join(', ') }}, max({{ order_col }}) as _mx
    from {{ this }}
    group by {{ grain_cols | join(', ') }}
)
select distinct t.*
from {{ this }} t
join _latest l
  on {% for c in grain_cols %}t.{{ c }} = l.{{ c }} and {% endfor %}t.{{ order_col }} = l._mx
{% endmacro %}
