# 공용 Gold AI 데이터 계약 v1

이 문서는 Weather Gold를 사람과 AI가 같은 의미로 읽기 위한 한국어 우선 선언 계약이다. SQL 식별자, 컬럼명, metadata key, enum token, relation ID, 명령은 안정적인 English token을 유지하고, 제품 질문·행 의미·사용 조건·시간·공간·단위·품질·조인·수명주기 설명은 한국어로 작성한다.

> **규범과 배포 현황은 다르다.** 아래 YAML은 안전한 v1 선언 형태를 보여 주는 규범 예시이며, 실제 Weather relation이 이 계약대로 배포되었다는 증거가 아니다. 기본 `contract_status`는 `dev_pending`이다. 이 문서 작성 시점에는 approved-dev physical proof와 data correctness proof를 수행하지 않았고, Snowflake 게시·Gold API·실제 application exposure도 배포하지 않았다.

| 구분 | v1 규범 | 이 문서 작성 시점의 실제 상태 |
| --- | --- | --- |
| 선언 기본값 | `contract_status: dev_pending` | 문서 예시에만 적용 |
| Weather 목표 제품 | 아래 의미·grain·품질 경계를 충족 | 현행 모델에는 명시한 propagation·제품 분리 gap이 있음 |
| 물리 relation 증거 | approved-dev 동일 invocation의 `manifest.json`·`catalog.json` 비교 필요 | `NOT_RUN` |
| 데이터 정합성 증거 | scoped SQL/data test와 수동 의미 리뷰 필요 | `NOT_RUN` |
| 소비 표면 | 실제 소비자가 있을 때만 `served` | Snowflake/API/application exposure 미배포 |

## 1. 계약의 목적과 안전한 추론 경계

공용 Gold 이름이나 컬럼명만으로 row meaning, grain, 시간 역할, 공간 기준, 단위, zero/null 의미, 조인 cardinality를 추측하면 안 된다. 소비자는 각 증거 층의 결과와 그 층이 증명하지 않는 것을 함께 읽어야 한다.

AI 소비자가 안전하게 추론할 수 있는 범위는 다음과 같다.

- source declaration `PASS`는 선택한 source schema YAML의 resource·column 설명, 한국어 표식, 보수적 문법 coverage와 source-file uniqueness 결과를 뜻한다.
- manifest declaration `PASS`는 dbt manifest v12에 v1 metadata shape, publication 정책, dependency/test name이 선언되었음을 뜻한다.
- approved-dev physical `PASS`는 operator가 제공한 동일 invocation catalog의 relation 컬럼명·타입·순서가 선언과 일치했다는 뜻이다.
- data correctness `PASS`는 별도로 실행한 정확한 SQL/test 범위 안에서만 grain, 최신 선택, completeness, 공간 stamp, zero/null, fan-out, reconciliation이 확인되었다는 뜻이다.

어느 자동 검사도 한국어 설명의 도메인 진실성, SQL projection, 단위 해석, 시간 변환, 공간 매핑, null/zero 맥락을 대신하지 않는다. `proof.manual_semantic_review`는 항상 `REQUIRED`이며 Gate B에서 SQL과 데이터 근거를 사람이 검토해야 한다.

## 2. 언어와 canonical metadata 위치

dbt 1.10 기준 canonical 위치는 모델의 `config.meta.public_gold`와 컬럼의 `config.meta`다. 이 형태는 dbt 공식 [meta resource config](https://docs.getdbt.com/reference/resource-configs/meta)를 따른다. validator가 legacy `meta`를 제한적으로 읽더라도 새 선언은 canonical 위치만 사용한다. canonical과 legacy 값이 다르면 `CONFLICTING_METADATA`로 실패한다.

`documentation_language`는 정확히 `ko-KR`이어야 한다. 다음 항목은 한국어 문장이어야 한다.

- model·column `description`
- `product_question`, `row_meaning`, `grain`, `anchor_universe`
- `usage_guidance`, `do_not_use_for`, `semantic_caveats`, `owner`
- time·space·join·quality·lifecycle의 의미 설명
- `published_producer`의 `cross_domain_usage_examples`

SQL 식별자, metadata key, enum token, `unique_id`, source/model relation ID, timezone, 명령은 English token을 유지한다. 설명은 식별자만 반복하거나 미완성 표식으로 끝내지 않는다. 한국어 문자가 들어 있다는 사실만으로 의미가 옳다고 판정하지 않는다.

### 2.1 Source YAML 문법과 fail-closed 경계

parse 전 source linter가 지원하는 문법은 다음으로 제한한다.

- space-indented block mapping과 block sequence
- plain scalar와 single/double quoted scalar
- comment
- literal/folded block scalar
- balanced one-line non-nested scalar flow list와 flow map

anchor, alias, merge key, tab, nested flow, multiline flow, unbalanced flow, unclassified indentation은 지원하지 않는다. 하나라도 발견하면 해당 파일 전체를 `FAIL`로 처리하며, 검사 가능한 일부 resource만 성공으로 남기는 partial success를 허용하지 않는다. deterministic coverage가 `100%` 미만이면 전체 결과는 `PASS`가 될 수 없다. 반대로 `coverage_percentage=100`은 scanner가 예상 구조를 모두 방문했다는 뜻일 뿐 description 존재나 의미 진실성의 증거는 아니다.

## 3. 정확한 v1 vocabulary

### 3.1 모델 수준

| 영역 | key와 허용값 | 규칙 |
| --- | --- | --- |
| 버전·언어 | `contract_version`, `documentation_language: ko-KR` | 둘 다 필수 |
| 소유·성숙도 | `owner`, `maturity: low\|medium\|high` | `owner`는 한국어 설명 |
| 공개 상태 | `visibility: internal\|candidate\|published_producer\|served` | 실제 소비 상태와 일치해야 함 |
| 실행 계약 | `contract_status: dev_pending\|enforced` | 기본은 `dev_pending` |
| 식별 | `primary_key`, `column_order` | 비어 있지 않은 ordered list |
| 제품 의미 | `product_question`, `row_meaning`, `grain`, `anchor_universe` | 한국어 필수 |
| 사용 경계 | `usage_guidance`, `do_not_use_for`, `semantic_caveats` | 한국어 필수 |
| 구조 | `time`, `space`, `metrics`, `joins`, `quality`, `lineage`, `lifecycle` | 일곱 key 모두 mapping이어야 함 |

`primary_key`는 중복 없는 선언 컬럼 목록이다. 각 key column은 `semantic_role`이 `key`, `primary_key`, `join_key`, `dimension_key`, `foreign_key`, `identifier` 중 하나여야 하고 `nullable: false`를 선언해야 한다.

`column_order`는 선언한 모든 컬럼을 정확히 한 번씩 포함한다. manifest mapping의 insertion order나 schema YAML의 배치 순서를 물리 순서로 추정하지 않는다. 공식 [dbt manifest v12 schema](https://schemas.getdbt.com/dbt/manifest/v12.json)의 `ColumnInfo`에는 physical `index`가 없지만, [dbt catalog v1 schema](https://schemas.getdbt.com/dbt/catalog/v1.json)의 `ColumnMetadata`에는 `name`, `type`, `index`가 required다. 따라서 선언 순서의 정본은 `public_gold.column_order`, 물리 순서의 근거는 catalog v1 `index`다.

### 3.2 컬럼 수준

모든 공개 컬럼은 다음을 갖는다.

| 위치 | key | 규칙 |
| --- | --- | --- |
| column | `description` | 한국어 의미 설명 |
| column | `data_type` | 비어 있지 않은 물리 타입 선언 |
| `config.meta` | `semantic_role` | 비어 있지 않은 stable token |
| `config.meta` | `null_meaning` | 한국어 null 의미 |
| `config.meta` | `nullable` | 있으면 boolean, primary key는 반드시 `false` |
| metric column `config.meta` | `unit`, `zero_meaning`, `aggregation_behavior` | model `metrics`와 일치 |
| governed timestamp `config.meta` | `time_role`, `timezone: Asia/Seoul` | model `time.roles`와 일치 |

### 3.3 시간

`time`은 다음 key를 사용한다.

- `canonical_timezone: Asia/Seoul`
- 한국어 `freshness_slo`, `as_of_meaning`, `late_repair_policy`
- `roles.<column>.time_role`
- `roles.<column>.timezone: Asia/Seoul`

timestamp data type, `_at` suffix, `semantic_role: timestamp`, 또는 column의 `time_role`/`timezone` 중 하나라도 해당하면 governed time column이다. 모든 governed time column은 timestamp data type, `semantic_role: timestamp`, column과 model 양쪽의 동일한 `time_role`, `Asia/Seoul`을 가져야 한다.

### 3.4 공간

`space.enabled: false`는 공간축을 게시하지 않는 제품에만 사용한다. `space.enabled: true`이면 다음 전체가 필수다.

- exact `source_chain`
- `canonical_key: admin_dong_code`
- `revision_field: admin_dong_revision_date`
- exact `stamp_fields`
- 한국어 `candidate_key_explanation`, `mapping_version_explanation`, `null_location_explanation`, `fan_out_explanation`
- 서로 다른 이름의 `reconciliation_tests` 두 개 이상
- model의 직접 `dim_admin_dong` dependency

exact chain과 stamp는 다음과 같다.

```text
iceberg_dev.common.bronze_admin_dong_master
  -> asac_axes.dim_admin_dong

admin_dong_code
admin_dong
gu_code
gu
admin_dong_revision_date
```

`dim_admin_dong.revision_date`는 공용 Gold에서 `admin_dong_revision_date`로 명시적으로 alias·stamp한다. 원천 code, boundary seed, centroid, 명칭만으로 canonical stamp 완료를 주장하지 않는다.

### 3.5 metric

`metrics.<column>`은 `semantic_role: metric`인 모든 컬럼을 정확히 설명한다.

- `expression`, `formula`, `source_expression` 중 하나 이상
- `unit`
- `aggregation`
- `denominator`
- 한국어 `zero_meaning`, `null_meaning`
- `additive_axes`, `non_additive_axes`

model metric의 `unit`, `aggregation`, `zero_meaning`, `null_meaning`은 column `config.meta`의 `unit`, `aggregation_behavior`, `zero_meaning`, `null_meaning`과 일치한다. 각 axis list에는 중복이 없어야 하고 두 목록의 교집합도 없어야 한다.

### 3.6 join

`joins.<name>`은 다음 key를 모두 갖는다.

- `target`
- ordered `source_keys`
- 한국어 `purpose`
- `cardinality: one_to_one|many_to_one`
- 한국어 `fan_out_policy`
- `reconciliation_test`

공개 join에는 `one_to_many`와 `many_to_many`를 허용하지 않는다. `reconciliation_test` 이름은 manifest에서 해당 model에 의존하는 test node 하나에 정확히 해소되어야 한다.

### 3.7 품질

`quality`는 한국어 `completeness_explanation`, `freshness_explanation`, `coverage_explanation`과 `state_fields`를 갖는다. 각 `state_fields.<column>`은 다음 shape다.

- `allowed_values`: 중복 없는 lowercase `snake_case` token 목록
- `state_explanations`: allowed token과 exact-set으로 일치하는 한국어 설명 mapping

`coverage_percentage=100`은 source scanner가 예상 구조를 모두 방문했다는 뜻일 뿐, description 존재·의미 진실성·물리 relation·데이터 정합성의 증거가 아니다. top-level `status`, `errors`, `description_fields_present`, proof tuple을 함께 읽는다.

### 3.8 lineage

`lineage.source_relations`는 하나 이상의 stable relation ID를 갖는다. `lineage.identifiers`는 다음 다섯 class를 모두 선언한다.

- `as_of`
- `publication`
- `raw`
- `request`
- `run`

각 class는 선언 컬럼의 `columns` 목록을 사용하거나, relation 단위 근거만 있을 때 `relation_level_only: true`와 누락 또는 빈 `columns`를 사용한다. relation-level 선언에 실제 column을 함께 넣지 않는다.

### 3.9 lifecycle

`lifecycle.status`는 `active|deprecated`다. `deprecated`는 `replacement_relation`과 한국어 `compatibility_window_guidance`가 필수다. `active` relation이 미래 replacement를 미리 알릴 때는 `replacement_is_future: true`가 필요하다.

### 3.10 export safety

model `config.meta.public_gold`와 column `config.meta`는 recursive export safety 검사를 받는다. `generated_at`, `environment_schema`, credential, token, secret, password, `access_key`, `private_key`, `api_key`, path 변형처럼 dynamic·sensitive·environment·filesystem 의미를 가진 key를 계약 metadata에 넣지 않는다. absolute filesystem path value도 금지한다.

`served` exposure가 catalog로 projection하는 `unique_id`, `name`, `type`, owner name/email scalar에도 absolute filesystem path와 runtime timestamp literal을 넣지 않는다. 실행 시각·환경 schema·credential을 계약 의미와 섞지 않고 외부 실행 증거와 운영 설정에 둔다.

## 4. publication과 exposure의 진실성

| `visibility` | public catalog export | exposure 정책 | 의미 |
| --- | --- | --- | --- |
| `internal` | 제외 | dependent exposure 금지 | 도메인 내부 작업물 |
| `candidate` | 제외 | dependent exposure 금지 | 공개 전 검증 후보 |
| `published_producer` | 포함 | `exposure_status: none_no_live_consumer`, live exposure 금지 | 재사용 가능한 producer 계약이지만 실제 application 소비자는 없음 |
| `served` | 포함 | `exposure_status: active_exposure`, 유효한 dependent manifest exposure 필수 | 실제 application 소비 경로가 존재 |

`published_producer`는 하나 이상의 `intended_consumer_types`와 한국어 `cross_domain_usage_examples` 두 개 이상을 선언한다. 계획 중인 dashboard, Snowflake, API, AI consumer를 live exposure로 선등록하지 않는다. `served` promotion은 nonempty exposure `name`·`type`, `maturity: low|medium|high`, nonempty owner name 또는 email, dependent lineage가 실제 manifest에 있을 때만 가능하다.

권장 promotion 순서는 `internal -> candidate -> published_producer -> served`다. promotion에는 해당 단계의 source·manifest 검증, 승인된 dev physical 비교, 필요한 data correctness test, 수동 의미 리뷰, 실제 consumer 존재가 모두 필요하다. 한 단계의 `PASS`를 다음 단계의 증거로 자동 승격하지 않는다.

## 5. 안전한 v1 block-YAML 규범 예시

다음 resource는 metadata shape를 설명하기 위한 예시다. relation 배포, SQL dependency, test node, 물리 catalog, 데이터 값의 존재를 주장하지 않는다. `reconcile_admin_dong_stamp`, `reconcile_admin_dong_revision`, `reconcile_admin_dong_join`이라는 별도 test node는 실제 구현 시 이 model에 직접 의존해야 한다.

```yaml
version: 2

models:
  - name: gold_public_admin_dong_metric_example
    description: 서울 행정동별 공개 지표와 품질 상태를 제공하는 규범 예시 모델입니다.
    config:
      meta:
        public_gold:
          contract_version: "1.0"
          documentation_language: ko-KR
          owner: 서울 데이터 제품 운영팀
          maturity: medium
          visibility: published_producer
          contract_status: dev_pending
          exposure_status: none_no_live_consumer
          intended_consumer_types:
            - analyst
            - ai_catalog
          cross_domain_usage_examples:
            - 교통 지표를 행정동 공통축으로 비교할 때 보조 지표로 사용합니다.
            - 문화 시설 분석에서 같은 행정동과 기준 시각의 지역 맥락을 설명합니다.
          product_question: 각 서울 행정동의 기준 시각별 공개 지표는 몇 건입니까?
          row_meaning: 서울 행정동 한 곳의 기준 시각별 공개 지표와 품질 상태 한 행입니다.
          grain: admin_dong_code와 product_as_of_at 조합마다 한 행입니다.
          anchor_universe: 정본 행정동 최신 개정과 게시 가능한 기준 시각의 조합입니다.
          usage_guidance: 행정동 단위 건수 비교와 추세 설명에 사용합니다.
          do_not_use_for: 개인의 위치나 행동을 추정하거나 실시간 경보를 판정하는 데 사용하지 않습니다.
          semantic_caveats: 지연 수집과 매핑 실패 상태를 quality_state와 함께 해석해야 합니다.
          primary_key:
            - product_row_id
          column_order:
            - product_row_id
            - admin_dong_code
            - product_as_of_at
            - admin_dong
            - gu_code
            - gu
            - admin_dong_revision_date
            - metric_value
            - quality_state
            - published_at
            - dag_run_id
            - raw_object_key
            - request_id
          time:
            canonical_timezone: Asia/Seoul
            freshness_slo: 게시 가능한 최신 증거를 15분 이내 반영하는 것을 목표로 합니다.
            as_of_meaning: 제품이 완전하다고 판정한 최신 증거 시각을 뜻합니다.
            late_repair_policy: 지연 자료는 승인된 후속 repair 범위에서 비파괴적으로 재처리하고 같은 검증을 반복합니다.
            roles:
              product_as_of_at:
                time_role: as_of
                timezone: Asia/Seoul
              published_at:
                time_role: publication
                timezone: Asia/Seoul
          space:
            enabled: true
            source_chain:
              - iceberg_dev.common.bronze_admin_dong_master
              - asac_axes.dim_admin_dong
            canonical_key: admin_dong_code
            revision_field: admin_dong_revision_date
            stamp_fields:
              - admin_dong_code
              - admin_dong
              - gu_code
              - gu
              - admin_dong_revision_date
            candidate_key_explanation: 원천 행정동 코드는 정본 조인 전 후보 키로만 사용합니다.
            mapping_version_explanation: 정본 행정동 개정일을 모든 게시 행에 함께 기록합니다.
            null_location_explanation: 매핑 실패 행은 후보 단계에서 stamp 전체를 null로 유지하고 공개 게시에서 격리합니다.
            fan_out_explanation: 정본 차원 조인으로 행 수가 늘어나면 게시를 중단합니다.
            reconciliation_tests:
              - reconcile_admin_dong_stamp
              - reconcile_admin_dong_revision
          metrics:
            metric_value:
              expression: sum(metric_value)
              unit: 건
              aggregation: sum
              denominator: not_applicable
              zero_meaning: 완전한 원천 증거에서 해당 행정동의 지표 건수가 없음을 뜻합니다.
              null_meaning: 완전성 또는 지표 값을 확인할 증거가 부족한 상태입니다.
              additive_axes:
                - admin_dong
              non_additive_axes:
                - time
          joins:
            admin_dong_dimension:
              target: model.asac_axes.dim_admin_dong
              source_keys:
                - admin_dong_code
              purpose: 행정동 코드의 정본 명칭과 개정일을 검증합니다.
              cardinality: many_to_one
              fan_out_policy: 대상 행정동 코드가 중복되면 공개 게시를 중단합니다.
              reconciliation_test: reconcile_admin_dong_join
          quality:
            completeness_explanation: 필수 원천 행과 실행 근거가 모두 도착했는지 설명합니다.
            freshness_explanation: product_as_of_at과 최신 게시 가능한 증거 시각의 차이를 설명합니다.
            coverage_explanation: 서울 정본 행정동 모집단의 누락 여부를 설명합니다.
            state_fields:
              quality_state:
                allowed_values:
                  - complete
                  - missing
                  - partial
                state_explanations:
                  complete: 필수 원천과 reconciliation 근거가 모두 확인된 상태입니다.
                  missing: 기준 시각의 필수 원천 증거가 없는 상태입니다.
                  partial: 일부 원천 또는 공간 매핑 근거만 확인된 상태입니다.
          lineage:
            source_relations:
              - source.ask_seoul.raw_public_metric
            identifiers:
              as_of:
                columns:
                  - product_as_of_at
              publication:
                columns:
                  - published_at
              raw:
                columns:
                  - raw_object_key
              request:
                columns:
                  - request_id
              run:
                columns:
                  - dag_run_id
          lifecycle:
            status: active
    columns:
      - name: product_row_id
        description: admin_dong_code, 구분자 |, product_as_of_at의 YYYY-MM-DDTHH:MM:SS.ffffff 표현을 순서대로 연결한 제품 행 식별자입니다.
        data_type: varchar
        config:
          meta:
            semantic_role: primary_key
            nullable: false
            null_meaning: 기본 키이므로 null을 허용하지 않습니다.
      - name: admin_dong_code
        description: 행안부 서울 행정동 10자리 정본 코드입니다.
        data_type: varchar
        config:
          meta:
            semantic_role: join_key
            nullable: false
            null_meaning: natural grain과 정본 공간 조인에 필수이므로 null을 허용하지 않습니다.
      - name: product_as_of_at
        description: 제품이 완전하다고 판정한 최신 증거의 서울 기준 시각입니다.
        data_type: timestamp(6)
        config:
          meta:
            semantic_role: timestamp
            nullable: false
            null_meaning: natural grain과 제품 기준 시각에 필수이므로 null을 허용하지 않습니다.
            time_role: as_of
            timezone: Asia/Seoul
      - name: admin_dong
        description: 정본 행정동 차원에서 가져온 행정동명입니다.
        data_type: varchar
        config:
          meta:
            semantic_role: spatial_stamp
            nullable: false
            null_meaning: 공개 게시 행에서는 정본 행정동명이 없을 수 없습니다.
      - name: gu_code
        description: 행정동 코드에서 확인한 행안부 자치구 5자리 코드입니다.
        data_type: varchar
        config:
          meta:
            semantic_role: spatial_stamp
            nullable: false
            null_meaning: 공개 게시 행에서는 정본 자치구 코드가 없을 수 없습니다.
      - name: gu
        description: 정본 행정동 차원에서 가져온 자치구명입니다.
        data_type: varchar
        config:
          meta:
            semantic_role: spatial_stamp
            nullable: false
            null_meaning: 공개 게시 행에서는 정본 자치구명이 없을 수 없습니다.
      - name: admin_dong_revision_date
        description: 행정동 정본 매핑에 사용한 원천 개정일입니다.
        data_type: date
        config:
          meta:
            semantic_role: spatial_stamp
            nullable: false
            null_meaning: 공개 게시 행에서는 정본 개정일이 없을 수 없습니다.
      - name: metric_value
        description: 해당 행정동과 기준 시각에서 확인한 공개 지표 건수입니다.
        data_type: bigint
        config:
          meta:
            semantic_role: metric
            nullable: true
            null_meaning: 완전성 또는 지표 값을 확인할 증거가 부족한 상태입니다.
            unit: 건
            zero_meaning: 완전한 원천 증거에서 해당 행정동의 지표 건수가 없음을 뜻합니다.
            aggregation_behavior: sum
      - name: quality_state
        description: 원천 완전성과 공간 reconciliation을 요약한 품질 상태입니다.
        data_type: varchar
        config:
          meta:
            semantic_role: quality_state
            nullable: false
            null_meaning: 품질 판정을 만들지 못한 행은 공개하지 않습니다.
      - name: published_at
        description: 이 제품 행을 게시한 서울 기준 시각입니다.
        data_type: timestamp(6)
        config:
          meta:
            semantic_role: timestamp
            nullable: false
            null_meaning: 게시 시각이 없는 행은 공개하지 않습니다.
            time_role: publication
            timezone: Asia/Seoul
      - name: dag_run_id
        description: 이 행의 원천 실행을 추적하는 DAG 실행 식별자입니다.
        data_type: varchar
        config:
          meta:
            semantic_role: lineage_id
            nullable: false
            null_meaning: 실행 식별자가 없는 행은 원천 실행으로 추적할 수 없습니다.
      - name: raw_object_key
        description: 이 행의 원본 객체를 추적하는 안정 식별자입니다.
        data_type: varchar
        config:
          meta:
            semantic_role: lineage_id
            nullable: false
            null_meaning: 원본 객체 식별자가 없으면 raw 원문으로 역추적할 수 없습니다.
      - name: request_id
        description: 이 행의 원천 API 요청을 추적하는 식별자입니다.
        data_type: varchar
        config:
          meta:
            semantic_role: lineage_id
            nullable: false
            null_meaning: 요청 식별자가 없으면 수집 요청으로 역추적할 수 없습니다.
```

이 예시는 model metadata와 column metadata의 완전한 shape만 보여 준다. v1은 primary key column에 safe key role을, governed timestamp에 `semantic_role: timestamp`를 각각 요구하므로 `product_as_of_at`를 primary key로 이중 선언하지 않는다. 대신 natural grain을 표준 직렬화한 `product_row_id`를 결정적 surrogate key로 선언한다. data correctness gate는 surrogate 유일성뿐 아니라 `admin_dong_code × product_as_of_at` natural grain 유일성과 surrogate 재현성을 따로 검증해야 한다. SQL의 `ref('asac_axes', 'dim_admin_dong')`, 실제 manifest dependency, test node, relation column, 값 정합성은 각각 별도로 증명한다.

## 6. 네 개의 증거 층

| 층 | `PASS`가 뜻하는 것 | 뜻하지 않는 것 |
| --- | --- | --- |
| 1. source declaration | source schema YAML의 resource/column 설명, 한국어 표식, conservative parse coverage, source-file uniqueness | manifest 반영, SQL, relation, 데이터 값 |
| 2. manifest declaration | v1 metadata shape, publication 정책, 선언 dependency와 test name | 물리 relation, SQL projection, 값 정합성 |
| 3. approved-dev physical catalog | 동일 invocation의 제공된 catalog에서 relation 컬럼명·타입·순서가 선언과 일치 | operator 승인 진위, SQL 로직, 데이터 값, domain truth |
| 4. data correctness | 별도 scoped SQL/test가 확인한 grain·최신성·completeness·공간·zero/null·fan-out·양방향 reconciliation | 문서나 manifest가 자동으로 대신하는 전체 의미 검증 |

proof 값은 `PASS|FAIL|NOT_RUN`을 그대로 사용한다. 실행되지 않은 검사를 성공으로 간주하지 않는다. top-level `ERROR`는 입력·artifact shape·I/O·출력 전달 문제로 검사를 신뢰할 수 없다는 뜻이며, proof를 `PASS`로 승격하지 않는다.

| 값 | 해석 |
| --- | --- |
| `PASS` | 해당 proof scope의 검사만 성공 |
| `FAIL` | 해당 proof scope에서 차이 또는 계약 위반 확인 |
| `NOT_RUN` | 그 proof는 실행되거나 성립하지 않음 |
| `REQUIRED` | `manual_semantic_review`를 생략할 수 없음 |

## 7. Weather 목표 계약과 현행 gap

Weather의 안전한 목표 질문은 다음과 같다.

> 특정 `admin_dong_code × forecast_at × category`에서 가장 최근 `issued_at`이 발표한 예보 표현과 값은 무엇인가?

목표 row grain은 `admin_dong_code × forecast_at × category`마다 한 행이다. 최신 선택의 정렬은 `issued_at desc`, `collected_at desc`, `raw_object_key desc`, `request_id desc`이며 네 방향을 생략하거나 adapter 기본 정렬에 맡기지 않는다. `nx`, `ny`, `source_grid_place_id`, five-field admin stamp, run/raw/request lineage를 함께 남긴다.

`issued_at`은 KMA `base_date + base_time`의 발표 시각, `forecast_at`은 `fcstDate + fcstTime`의 예보 대상 시각, `collected_at`은 해당 원천을 수집한 시각이다. 세 역할은 모두 `Asia/Seoul`로 governed하되 서로 대체하지 않는다. 최신 발표 선택에 `issued_at`을 사용하더라도 제품 grain의 시간축은 `forecast_at`이다.

PCP/SNO를 포함한 KMA 표현은 다음 일곱 상태를 분리한다.

| enum | 의미 | zero/null/range 경계 |
| --- | --- | --- |
| `explicit_none` | 원천이 강수·적설 없음으로 명시 | 숫자 `0`으로 재해석하지 않음 |
| `quantitative_exact` | 단위가 있는 확정 점값 | `value_num` 사용 가능, 0도 `explicit_none`과 동일하지 않음 |
| `quantitative_range` | 미만·이상·구간 표현 | `value_lower_bound`·`value_upper_bound`로만 해석 |
| `bare_numeric` | 단위 없는 숫자 원문 | 숫자는 보존하지만 공식 의미가 검증되지 않았고 0을 없음으로 해석하지 않음 |
| `qualitative_code` | PTY/SKY의 정성 코드 | 수치 강수량·적설량으로 합산하지 않음 |
| `missing` | 원천 값 부재 | 정상 zero와 다름 |
| `unparseable` | 알려진 규칙으로 분류하지 못한 표현 drift | 정상 값이나 zero로 대체하지 않음 |

`quantitative_range`에서 “이상”의 `value_upper_bound: null`은 상한이 없다는 뜻이지 missing이 아니다. “미만”의 lower bound 0은 구간 경계이지 명시적 무강수·무적설이 아니다. `value_num: null`만 보면 `explicit_none`, range, qualitative code, missing, unparseable을 구분할 수 없으므로 반드시 `value_representation`과 bounds를 함께 읽는다.

최신 publishable 발표 자체가 없는 상태는 `explicit_none`, 유효한 numeric zero, 정상 empty 결과와 다르다. 새 publishable 발표가 존재하더라도 이전 발표에 있던 `admin_dong_code × forecast_at × category` key가 새 발표에서 사라졌다면, 완전한 발표에서 의도적으로 제외된 것인지 수집·적재 누락인지 manifest/audit 근거로 판별해야 한다. expected→target 검사는 새 발표의 누락을, target→expected 검사는 이전 발표에서 남은 stale extra를 검출한다. stale extra 제거는 이 양방향 차이가 확인된 뒤 승인된 repair 경계에서 수행한다.

현행 코드에는 다음 gap이 있다.

- grid Silver는 `value_representation`, `value_num`, bounds, `qualitative_code`, `forecast_lead_hours`를 만든다.
- admin-dong Silver는 그 의미 컬럼을 projection하지 않으며, 현재 place Gold도 노출하지 않는다.
- 현재 공간축은 `dim_weather_place`의 후보 code를 사용하고, 직접 `dim_admin_dong` dependency와 `admin_dong_revision_date` stamp가 없다.
- 현재 reconciliation은 expected Silver에서 Gold 누락·차이를 찾지만 Gold에만 남은 stale extra row까지 양방향으로 증명하지 않으며, incremental merge의 명시적 삭제 경로도 확인되지 않는다.

따라서 위 Weather shape는 목표 계약이다. 현재 relation에 대해 PCP/SNO 의미 전파, exact common-axis stamp, physical/data proof가 완료되었다고 표현하지 않는다.


## 8. 공통 공간축과 reconciliation

공간 producer는 다음 세 조건을 함께 만족해야 한다.

1. exact common chain과 five-field stamp를 선언한다.
2. SQL에서 `dim_admin_dong`에 직접 의존하고 `revision_date`를 `admin_dong_revision_date`로 projection한다.
3. 서로 다른 두 개 이상의 named spatial reconciliation과 공개 join reconciliation을 실제 data test로 실행한다.

manifest `depends_on`은 그래프 선언 근거일 뿐이다. dependency가 존재해도 SQL이 five-field를 선택했는지, source candidate를 self-copy하지 않았는지, 값이 정본과 같은지 증명하지 않는다. catalog comment도 의미 증거가 아니다.

공개 join은 canonical dim 방향의 `many_to_one` 또는 `one_to_one`만 허용한다. grid-to-admin 또는 boundary mapping 내부 fan-out은 transformation의 별도 문제이며, 공개 consumer join의 안전한 cardinality로 승격하지 않는다. data correctness gate에서 expected→target과 target→expected 양방향 차이, stamp 값, revision, duplicate/fan-out을 확인한다.

## 9. 세 CLI와 정확한 proof 해석

세 도구의 JSON stdout은 process text encoding과 무관한 UTF-8 bytes로 전달되고, 한국어를 Unicode escape로 바꾸지 않으며, deterministic key order와 한 개의 trailing newline을 사용한다. 입력 mapping order, catalog comment, runtime `generated_at`은 stable contract bytes의 근거가 아니다.

출력 디렉터리는 먼저 만든다.

```bash
mkdir -p target/contracts
```

### 9.1 source declaration linter

```bash
python3 domains/weather/contracts/scripts/lint_schema_contract_source.py \
  --schema-root domains/weather/models/schema.yml \
  --schema-root domains/weather/models/sources.yml \
  --resource gold_weather_forecast_by_place \
  --require-language ko-KR \
  --output target/contracts/weather-source-declaration.json
```

- exit `0`: top-level `PASS`
- exit `1`: top-level `FAIL`
- exit `2`: top-level `ERROR` 또는 output delivery error
- `proof_scope: source_yaml_declaration`
- `proof.declared_contract`: source declaration 전체가 통과하면 `PASS`, 아니면 `FAIL`
- `proof.source_yaml_uniqueness`: duplicate/name/coverage 구조 경계가 통과하면 `PASS`, 아니면 `FAIL`
- `proof.physical_contract: NOT_RUN`
- `proof.data_contract: NOT_RUN`
- `proof.manual_semantic_review: REQUIRED`

언어 오류만 있는 전체 `FAIL`에서도 `source_yaml_uniqueness`가 `PASS`일 수 있다. `--output` 전달 자체가 실패하면 exit 2와 stderr가 발생할 수 있으므로 파일 존재나 이전 파일을 성공 증거로 재사용하지 않는다.

source report는 가능한 오류를 `file`, `resource_kind`, `resource_name`, `field`, `column`, source line에 연결하고, file/resource/description field별 deterministic coverage count를 제공한다. unaccounted 구조가 있으면 일부 description 결과만으로 성공 판정을 만들지 않는다.

### 9.2 manifest declaration validator

```bash
python3 domains/weather/contracts/scripts/validate_public_gold_manifest.py \
  --manifest target/manifest.json \
  --resource gold_weather_forecast_by_place \
  --require-language ko-KR \
  --output target/contracts/public-gold-declared-catalog.json
```

- exit `0`: `PASS`
- exit `1`: `FAIL`
- exit `2`: `ERROR`
- `proof_scope: manifest_declared_contract`
- `proof.declared_contract: PASS|FAIL`
- `proof.source_yaml_uniqueness: NOT_RUN`
- `proof.physical_contract: NOT_RUN`
- `proof.data_contract: NOT_RUN`
- `proof.manual_semantic_review: REQUIRED`

stdout은 validation report다. `--output` catalog는 declaration `PASS`일 때만 만든다. output delivery가 실패하면 top-level `ERROR`이면서 이미 계산한 `declared_contract: PASS`가 남을 수 있으므로 top-level status를 우선 gate한다.

manifest 오류는 `nodes.<unique_id>.config.meta.public_gold...` 또는 `nodes.<unique_id>.columns.<column>...`의 exact JSON path를 사용한다. 이 path가 정확하더라도 description의 도메인 진실성을 자동 증명하지 않는다.

### 9.3 manifest와 dbt catalog 비교

fixture 비교는 물리 증거로 승격하지 않는다.

```bash
python3 domains/weather/contracts/scripts/compare_public_gold_catalog.py \
  --manifest target/manifest.json \
  --catalog target/catalog.json \
  --resource gold_weather_forecast_by_place \
  --require-language ko-KR \
  --evidence-kind fixture \
  --output target/contracts/weather-fixture-comparison.json
```

승인된 dev 비교는 외부에서 실제 run으로 해소할 수 있는 비밀이 아닌 evidence ID를 사용한다. 값은 `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`를 만족해야 한다.

```bash
python3 domains/weather/contracts/scripts/compare_public_gold_catalog.py \
  --manifest target/manifest.json \
  --catalog target/catalog.json \
  --resource gold_weather_forecast_by_place \
  --require-language ko-KR \
  --evidence-kind approved_dev_catalog \
  --evidence-id "$APPROVED_DEV_EVIDENCE_ID" \
  --output target/contracts/weather-physical-comparison.json
```

- exit `0`: comparison `PASS`
- exit `1`: comparison `FAIL`
- exit `2`: artifact shape·evidence·I/O `ERROR`
- `proof_scope: supplied_dbt_catalog_artifact_comparison`
- `proof.declared_contract: PASS|FAIL|NOT_RUN`
- `proof.catalog_comparison: PASS|FAIL|NOT_RUN`
- `proof.source_yaml_uniqueness: NOT_RUN`
- fixture의 `proof.physical_contract`는 comparison이 `PASS`여도 `NOT_RUN`
- 유효한 `approved_dev_catalog`의 `proof.physical_contract`는 comparison과 같은 `PASS|FAIL`
- `proof.data_contract: NOT_RUN`
- `proof.manual_semantic_review: REQUIRED`

comparator는 같은 dbt invocation의 `manifest.metadata.invocation_id`와 `catalog.metadata.invocation_id`가 정확히 같아야 한다. missing/extra column, type, 1부터 N까지 연속인 physical `index`, `public_gold.column_order`와의 순서를 비교한다. type 정규화는 대소문자·공백과 `int -> integer`, `double precision -> double`만 허용하고 precision·length·timezone 차이는 보존한다.

### 9.4 approved-dev consumer gate

`approved_dev_catalog`는 `operator_supplied_unverified` attestation이다. consumer는 `physical_contract` 하나만 읽으면 안 된다. 다음 전체 tuple이 동시에 성립하고 evidence ID가 외부 실행 기록으로 실제 해소될 때만 physical gate를 통과시킨다.

```text
status == PASS
proof.declared_contract == PASS
proof.catalog_comparison == PASS
proof.physical_contract == PASS
proof.source_yaml_uniqueness == NOT_RUN
proof.data_contract == NOT_RUN
proof.manual_semantic_review == REQUIRED
evidence.attestation == operator_supplied_unverified
evidence.evidence_scope == operator_asserted_approved_dev_catalog
evidence.evidence_id는 allowlist와 일치하고 외부 run ledger에서 해소됨
```

이 tuple은 comparator 자체의 physical gate다. 전체 publication gate는 별도 source linter의 top-level `PASS`, `proof.declared_contract: PASS`, `proof.source_yaml_uniqueness: PASS`도 요구한다. output delivery가 실패하면 이미 계산한 `catalog_comparison`·`physical_contract`가 남아도 top-level `status`가 `ERROR`가 될 수 있다. 이 경우 consumer gate는 실패다. operator 승인 진위, warehouse 실행, SQL projection, 데이터 값은 comparator가 암호학적으로 확인하지 않는다.

## 10. 물리·데이터 proof 절차

approved-dev 검증은 개인 소유의 고유 run-scoped smoke schema에서만 수행한다. schema 이름은 `dev_<owner_slug>_weather_contract_test_<run_token>` 형식을 사용한다. `owner_slug`는 인증된 GitHub ID를 lowercase로 바꾸고 `[a-z0-9_]` 밖의 문자를 `_`로 치환한 1~39자 값이다. `run_token`은 실행마다 새 UUID4에서 얻은 24자리 lowercase hexadecimal 값으로 고정하며 `^[a-f0-9]{24}$`를 만족해야 한다. 최종 schema 이름은 96자를 넘지 않아야 한다. 외부 evidence ID를 단순 치환해 `run_token`으로 사용하지 않는다. `run-a`, `run.a`, `run_a`처럼 서로 다른 ID가 같은 namespace로 충돌할 수 있기 때문이다.

writer 시작 전 namespace가 없음을 확인한다. 이미 존재하면 동일한 owner·`run_token`·evidence ID가 외부 run ledger에 연결된 명시적 retry인 경우만 재사용하고, 그 외에는 fail closed한다. 기존 namespace를 자동 삭제하거나 다른 실행의 namespace를 재사용하지 않는다. comparator report에는 allowlist를 통과한 외부 evidence ID 원문을 보존하고, ledger에 schema 이름·owner·`run_token`·evidence ID·dbt invocation ID의 mapping을 기록한다. 이 규칙으로 회사 스케줄 DAG와 writer가 사용하는 공유·운영 relation과 격리한다. prod write는 금지한다. teardown은 검증 실행과 분리해 별도 승인과 삭제 증거를 남긴다. 이 G0 문서 작업에서는 실제 smoke를 실행하지 않았으므로 physical/data smoke는 `NOT_RUN`이다.

1. 동일한 승인된 scoped dev invocation에서 dbt artifact를 생성하고 `manifest.json`과 `catalog.json`의 `invocation_id`를 보존한다.
2. source linter로 parse 전 duplicate·설명·언어·coverage를 확인한다.
3. manifest validator로 v1 declaration과 publication truthfulness를 확인한다.
4. comparator를 `approved_dev_catalog`와 외부 evidence ID로 실행해 physical name/type/order를 비교한다.
5. 별도 data test로 primary grain uniqueness, 최신 선택과 tie-break, publishable/completeness, freshness/coverage, common-axis stamp, zero/null, join cardinality, fan-out, expected↔target 양방향 reconciliation을 확인한다.
6. SQL·단위·시간·공간·null/zero·join 의미를 수동 검토하고 각 층을 `PASS|FAIL|NOT_RUN`으로 따로 기록한다.

오래된 manifest와 새 catalog를 조합하거나, fixture comparison을 approved-dev physical proof로 표현하지 않는다. 승인된 warehouse 실행이 없으면 physical/data proof는 `NOT_RUN`이다.

## 11. UTC description WATCH

현재 manifest validator는 `Asia/Seoul` governed timestamp description에서 ASCII identifier boundary의 독립 `UTC` token을 보수적으로 거절한다. “원천 UTC를 서울 기준 시각으로 변환했다”처럼 사실인 문장도 false positive가 될 수 있다. 한국어와 붙어 있는 token도 ASCII boundary 규칙상 탐지될 수 있다.

v1 설명에는 “원천 시간대를 서울 기준 시각으로 변환한 값”처럼 작성하되, 이 문구 회피를 시간 의미 증명으로 간주하지 않는다. 수동 semantic review는 계속 `REQUIRED`다. 후속 계약은 prose heuristic 대신 structured `source_timezone`와 `conversion_policy`를 검토할 수 있지만, 두 key는 v1 field가 아니며 현재 예시에 추가하지 않는다.

## 12. dev·consumer gate 뒤에 남기는 기능

다음 항목은 문서가 존재하거나 validator가 `PASS`했다는 이유만으로 활성화하지 않는다.

| 항목 | 현재 경계 | 활성화 전 조건 |
| --- | --- | --- |
| `contract.enforced` | 기본 `dev_pending` | effective dbt `config.contract.enforced: true`, adapter dev smoke, incremental `on_schema_change` 영향 검증 |
| global `NOT NULL` | 전역 강제하지 않음 | 합법적인 null·partial·missing 상태를 보존하는 column별 근거 |
| `persist_docs` | 전역 활성화하지 않음 | Trino/Data Catalog comment 동작과 rollback 검증 |
| Snowflake publication | 미배포 | 별도 저장 계층·adapter·보안·소유 이슈 승인 |
| Gold API·AI serving | 미배포 | 실제 consumer, 접근 정책, versioning, 운영 SLO |
| application exposure | 계획 소비처는 등록하지 않음 | 실제 dependent application이 있을 때 `served`로 promotion |

`late_repair_policy`는 정책 선언이지 repair 실행 권한이 아니다. destructive full refresh, backfill, cutoff repair, Airflow DAG gate는 후속 소유 이슈에서 별도로 승인·검증한다. 이 v1 문서는 DAG를 실행하거나 repair 경로를 구현하지 않는다.

## 13. reference ledger

### ASAC-DBT

- [Issue #48 — Silver 공통축](https://github.com/ASAC-DE-bigkk/ASAC-DBT/issues/48)
- [PR #49 — asac_axes 공용 패키지](https://github.com/ASAC-DE-bigkk/ASAC-DBT/pull/49)
- [PR #109 — common schema 전환](https://github.com/ASAC-DE-bigkk/ASAC-DBT/pull/109)
- [PR #138 — Weather Gold on_schema_change fail](https://github.com/ASAC-DE-bigkk/ASAC-DBT/pull/138)
- [Issue #144 — 공용 한국어 AI Gold 계약](https://github.com/ASAC-DE-bigkk/ASAC-DBT/issues/144)
- [PR #142 — Weather incremental Silver WIP 문맥](https://github.com/ASAC-DE-bigkk/ASAC-DBT/pull/142)

### ASAC-DAG

- [Issue #154 — 공통 행정동 마스터 수집](https://github.com/ASAC-DE-bigkk/ASAC-DAG/issues/154)
- [PR #159 — 행정동 마스터 수집 DAG](https://github.com/ASAC-DE-bigkk/ASAC-DAG/pull/159)
- [PR #160 — 수집 주기 weekly 조정](https://github.com/ASAC-DE-bigkk/ASAC-DAG/pull/160)
- [Issue #168 — Weather late/backfill 안전장치](https://github.com/ASAC-DE-bigkk/ASAC-DAG/issues/168)
- [PR #255 — Bronze common schema 전환](https://github.com/ASAC-DE-bigkk/ASAC-DAG/pull/255)

### dbt 공식 계약 근거

- [meta](https://docs.getdbt.com/reference/resource-configs/meta)
- [model contracts](https://docs.getdbt.com/reference/resource-configs/contract)
- [exposures](https://docs.getdbt.com/docs/build/exposures)
- [persist_docs](https://docs.getdbt.com/reference/resource-configs/persist_docs)
- [manifest v12 JSON schema](https://schemas.getdbt.com/dbt/manifest/v12.json)
- [catalog v1 JSON schema](https://schemas.getdbt.com/dbt/catalog/v1.json)
