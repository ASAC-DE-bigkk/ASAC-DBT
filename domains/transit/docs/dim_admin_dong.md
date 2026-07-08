# dim_admin_dong — 서울 행정동 차원 (공통, asac_axes)

- **한 행** = 서울 행정동 1개 / **키**: `admin_dong_code`(행안부 10자리) / 426행
- **원천**: 공공데이터포털 odcloud 법정동 연계정보 @weekly → `bronze_admin_dong_master` 최신 개정(2025-04-01)
- **팀 공통축의 기준 테이블** — 모든 도메인의 공간 조인이 이 코드 체계로 수렴

## 컬럼

| 컬럼 | 설명 |
|---|---|
| `admin_dong_code` | 행안부 행정동 10자리 — **canonical 조인 키** (선행 0 보존, varchar) |
| `admin_dong` | 행정동명("소공동") |
| `gu_code` / `gu` | 자치구 5자리(코드 앞 5자리) / 구명 |
| `stat_region_cd` | 통계청 지역 코드 (7자리 체계 도메인과의 alias 다리) |
| `latitude` / `longitude` | 행정동 중심 좌표 (crosswalk seed 보조 — 6개 동은 null) |
| `revision_date` | 행안부 개정 기준일 |

## 활용 추천

1. **모든 동 단위 집계의 뼈대**: fact를 집계한 뒤 이 dim에 **left join이 아니라 dim을 왼쪽에** 두면 "데이터가 없는 동"도 0으로 표현돼 지도가 빈칸 없이 그려짐.
2. **구 단위 롤업**: `gu_code`로 group by — 동→구 전환은 항상 이 dim 기준.
3. **통계청 자료 연계**: `stat_region_cd`로 7자리 체계(인구 통계 등) 조인.
4. **동 중심점 지도 마커**: 폴리곤 없이 간단히 점 지도를 그릴 때 `latitude/longitude` 사용.

## 주의

- 행정동은 개정된다(연 수회) — `revision_date` 다르면 코드 재편 가능. 시계열 장기 비교 시 개정 이력 인지.
- 좌표 null 6개 동은 seed 미매칭(행정동 재편) — 점 지도에서만 영향, 코드 조인은 무관.
