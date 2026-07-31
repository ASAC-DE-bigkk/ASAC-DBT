# Traffic Publishability Prod Guard Removal Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** prod에서도 Traffic incident Silver publishability reconcile을 dev와 동일한 안전 계약으로 실행한다.

**Architecture:** 환경명·catalog·schema를 고정한 컴파일 차단만 제거한다. `source_record_id` 고유키, NULL·중복 preflight, 최신 SUCCESS·publishable manifest 필터, stale lineage 교체 방지, 단일 `MERGE`는 유지한다.

**Tech Stack:** dbt-core, dbt-trino, Jinja SQL macro, pytest

---

### Task 1: prod 컴파일 회귀를 재현한다

- [ ] `domains/traffic_weather/macros/traffic/traffic_publishability_reconcile.sql`의 현재 prod 차단을 확인한다.
- [ ] prod target으로 incident Silver를 compile하여 dev-only compiler error가 발생하는지 확인한다.

### Task 2: 환경 고정 가드만 제거한다

- [ ] `domains/traffic_weather/macros/traffic/traffic_publishability_reconcile.sql`에서 `traffic_publishability_assert_dev_target`과 호출만 제거한다.
- [ ] 기존 reconcile 안전 계약 테스트를 실행한다.
- [ ] prod target compile이 성공하는지 확인한다.

### Task 3: 저장소 검증과 배포 준비

- [ ] Traffic 관련 pytest를 실행한다.
- [ ] `git diff --check`와 변경 범위 검토로 다른 도메인 비영향을 확인한다.
- [ ] commit, push, dev PR, CI 확인 후 병합한다.
