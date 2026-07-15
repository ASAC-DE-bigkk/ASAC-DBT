from contracts.engine.tests.fixtures import (
    Path,
    VALID_MIXED_SCHEMA,
    errors_with_code,
    json,
    lint,
    tempfile,
    unittest,
    write_yaml,
)


class SchemaContractSourceLinterSemanticTests(unittest.TestCase):
    def test_valid_mixed_schema_passes_with_complete_utf8_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            schema_path = write_yaml(root, "nested/schema.yml", VALID_MIXED_SCHEMA)

            report = lint.lint_schema_contracts([root], required_language="ko-KR")
            encoded = lint.render_report(report)

            self.assertEqual("PASS", report["status"])
            self.assertEqual([], report["errors"])
            self.assertEqual(
                {
                    "coverage_percentage": 100.0,
                    "description_fields_accounted": 9,
                    "description_fields_expected": 9,
                    "description_fields_present": 9,
                    "description_fields_unaccounted": 0,
                    "error_count": 0,
                    "files_scanned": 1,
                    "files_total": 1,
                    "resources_scanned": 5,
                    "resources_total": 5,
                    "resources_unaccounted": 0,
                },
                report["summary"],
            )
            self.assertEqual(
                schema_path.resolve().as_posix(), report["files"][0]["path"]
            )
            self.assertEqual("PASS", report["files"][0]["scan_status"])
            self.assertEqual(
                [
                    ("model", "gold_weather_orders"),
                    ("model", "quoted_model"),
                    ("seed", "area_seed"),
                    ("source", "source:public_api"),
                    ("source_table", "source:public_api.events"),
                ],
                [(item["kind"], item["name"]) for item in report["resources"]],
            )
            self.assertIn("서울", encoded)
            self.assertNotIn("\\u", encoded)
            json.loads(encoded)

            descriptions = report["descriptions"]
            self.assertEqual(9, len(descriptions))
            self.assertTrue(all(item["accounted"] for item in descriptions))
            self.assertTrue(all(item["present"] for item in descriptions))
            self.assertTrue(
                all(item["language_status"] == "PASS" for item in descriptions)
            )

    def test_cross_file_duplicates_use_nearest_project_scope_and_report_both_locations(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first_project = root / "project-a"
            second_project = root / "project-b"
            write_yaml(first_project, "dbt_project.yml", "name: project_a\n")
            write_yaml(second_project, "dbt_project.yml", "name: project_b\n")
            first = write_yaml(
                first_project,
                "models/a.yml",
                """
                version: 2
                models:
                  - name: shared_model
                    description: 첫 번째 모델 설명
                seeds:
                  - name: shared_seed
                    description: 첫 번째 시드 설명
                sources:
                  - name: shared_source
                    description: 첫 번째 원천 설명
                    tables:
                      - name: shared_table
                        description: 첫 번째 원천 테이블 설명
                """,
            )
            second = write_yaml(
                first_project,
                "models/b.yml",
                """
                version: 2
                models:
                  - name: shared_model
                    description: 두 번째 모델 설명
                seeds:
                  - name: shared_seed
                    description: 두 번째 시드 설명
                sources:
                  - name: shared_source
                    description: 두 번째 원천 설명
                    tables:
                      - name: shared_table
                        description: 두 번째 원천 테이블 설명
                """,
            )
            write_yaml(
                second_project,
                "models/schema.yml",
                """
                version: 2
                models:
                  - name: shared_model
                    description: 다른 프로젝트의 모델 설명
                seeds:
                  - name: shared_seed
                    description: 다른 프로젝트의 시드 설명
                sources:
                  - name: shared_source
                    description: 다른 프로젝트의 원천 설명
                    tables:
                      - name: shared_table
                        description: 다른 프로젝트의 원천 테이블 설명
                """,
            )

            forward = lint.lint_schema_contracts(
                [second_project, first_project], required_language="ko-KR"
            )
            reverse = lint.lint_schema_contracts(
                [first_project, second_project], required_language="ko-KR"
            )

            self.assertEqual(lint.render_report(forward), lint.render_report(reverse))
            duplicates = errors_with_code(forward, "DUPLICATE_RESOURCE")
            self.assertEqual("FAIL", forward["status"])
            self.assertEqual("FAIL", forward["proof"]["source_yaml_uniqueness"])
            self.assertEqual(4, len(duplicates), duplicates)
            expected_names = {
                ("model", "shared_model"),
                ("seed", "shared_seed"),
                ("source", "source:shared_source"),
                ("source_table", "source:shared_source.shared_table"),
            }
            self.assertEqual(
                expected_names,
                {
                    (error["resource_kind"], error["resource_name"])
                    for error in duplicates
                },
            )
            for error in duplicates:
                self.assertEqual(
                    [first.resolve().as_posix(), second.resolve().as_posix()],
                    error["files"],
                )
                self.assertEqual(2, len(error["lines"]))
                self.assertEqual(
                    first_project.resolve().as_posix(), error["project_scope"]
                )

            ambiguous = lint.lint_schema_contracts(
                [first_project, second_project],
                resources=["shared_model"],
                required_language="ko-KR",
            )
            self.assertEqual("FAIL", ambiguous["status"])
            selector_errors = errors_with_code(ambiguous, "RESOURCE_SELECTOR_AMBIGUOUS")
            self.assertEqual(1, len(selector_errors))
            self.assertEqual(
                [
                    first_project.resolve().as_posix(),
                    second_project.resolve().as_posix(),
                ],
                selector_errors[0]["project_scopes"],
            )

    def test_placeholders_must_be_the_whole_description_and_controlled_codes_are_prose(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = write_yaml(
                root,
                "semantic.yml",
                """
                version: 2
                models:
                  - name: todo_suffix
                    description: TODO입니다
                  - name: tbd_suffix
                    description: TBD임
                  - name: placeholder_suffix
                    description: placeholder 예정
                  - name: controlled_pending
                    description: "`PENDING` 상태의 의미를 설명합니다"
                  - name: controlled_unknown
                    description: 미정 상태는 null로 저장합니다
                """,
            )

            report = lint.lint_schema_contracts([path], required_language="ko-KR")

            placeholder_names = {
                error["resource_name"]
                for error in errors_with_code(report, "PLACEHOLDER_DESCRIPTION")
            }
            self.assertEqual(
                {"todo_suffix", "tbd_suffix", "placeholder_suffix"}, placeholder_names
            )
            self.assertFalse(
                {"controlled_pending", "controlled_unknown"} & placeholder_names,
                report,
            )

    def test_placeholder_wrappers_and_deferred_variants_fail_but_real_sentences_pass(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = write_yaml(
                root,
                "placeholder-wrappers.yml",
                """
                version: 2
                models:
                  - name: backtick_todo
                    description: "`TODO`입니다"
                  - name: backtick_tbd
                    description: "`TBD`임"
                  - name: curly_todo
                    description: “TODO”입니다
                  - name: bracket_unknown
                    description: 「미정」입니다
                  - name: combined_deferred
                    description: TODO - 추후 작성
                  - name: later_deferred
                    description: 나중에 작성
                  - name: actual_todo_semantics
                    description: "`TODO`는 원천 시스템의 정상 상태 코드입니다"
                  - name: actual_later_sentence
                    description: 나중에 수집된 값은 ingest_at으로 구분합니다
                """,
            )

            report = lint.lint_schema_contracts([path], required_language="ko-KR")

            placeholders = {
                error["resource_name"]
                for error in errors_with_code(report, "PLACEHOLDER_DESCRIPTION")
            }
            self.assertEqual(
                {
                    "backtick_todo",
                    "backtick_tbd",
                    "curly_todo",
                    "bracket_unknown",
                    "combined_deferred",
                    "later_deferred",
                },
                placeholders,
            )
            self.assertFalse(
                {"actual_todo_semantics", "actual_later_sentence"} & placeholders,
                report,
            )

    def test_placeholder_allowlist_grammar_handles_wrappers_and_compounds_only(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = write_yaml(
                root,
                "placeholder-grammar.yml",
                """
                version: 2
                models:
                  - name: ascii_paren
                    description: (TODO)입니다
                  - name: fullwidth_paren
                    description: （TODO）입니다
                  - name: square_wrapper
                    description: 【미정】입니다
                  - name: markdown_bold
                    description: "**TODO**입니다"
                  - name: markdown_underline
                    description: "__TBD__임"
                  - name: slash_compound
                    description: TODO / 추후 작성
                  - name: colon_compound
                    description: "TODO : 추후 작성"
                  - name: dash_compound
                    description: TODO-추후 작성
                  - name: later_scheduled
                    description: 나중에 작성 예정
                  - name: enum_prose
                    description: "`TODO`는 원천 시스템의 정상 상태 코드입니다"
                  - name: later_prose
                    description: 나중에 수집된 값은 ingest_at으로 구분합니다
                  - name: punctuation_prose
                    description: TODO 상태는 원천 코드이며 미정 값은 null입니다
                """,
            )
            report = lint.lint_schema_contracts([path], required_language="ko-KR")
            placeholders = {
                error["resource_name"]
                for error in errors_with_code(report, "PLACEHOLDER_DESCRIPTION")
            }
            self.assertEqual(
                {
                    "ascii_paren",
                    "fullwidth_paren",
                    "square_wrapper",
                    "markdown_bold",
                    "markdown_underline",
                    "slash_compound",
                    "colon_compound",
                    "dash_compound",
                    "later_scheduled",
                },
                placeholders,
            )
            self.assertFalse(
                {"enum_prose", "later_prose", "punctuation_prose"} & placeholders,
                report,
            )

    def test_wrapped_placeholders_allow_only_terminal_punctuation_after_suffix(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = write_yaml(
                root,
                "placeholder-terminal.yml",
                """
                version: 2
                models:
                  - name: backtick_period
                    description: "`TODO`입니다."
                  - name: paren_bang
                    description: (TODO)입니다!
                  - name: bracket_stop
                    description: 【미정】입니다。
                  - name: markdown_question
                    description: "**TODO**입니다?"
                  - name: prose_period
                    description: "`TODO`는 원천 상태 코드입니다."
                  - name: prose_bang
                    description: 미정 상태는 null로 저장합니다!
                """,
            )
            report = lint.lint_schema_contracts([path], required_language="ko-KR")
            placeholders = {
                error["resource_name"]
                for error in errors_with_code(report, "PLACEHOLDER_DESCRIPTION")
            }
            self.assertEqual(
                {"backtick_period", "paren_bang", "bracket_stop", "markdown_question"},
                placeholders,
            )
            self.assertFalse({"prose_period", "prose_bang"} & placeholders, report)

    def test_unaccounted_structure_reduces_coverage_but_missing_description_is_accounted(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            missing_description = write_yaml(
                root,
                "missing-description.yml",
                """
                version: 2
                models:
                  - name: documented_later
                """,
            )
            missing_report = lint.lint_schema_contracts(
                [missing_description], required_language="ko-KR"
            )
            self.assertEqual(100.0, missing_report["summary"]["coverage_percentage"])
            self.assertEqual(
                0, missing_report["summary"]["description_fields_unaccounted"]
            )

            nameless_column = write_yaml(
                root,
                "nameless-column.yml",
                """
                version: 2
                models:
                  - name: model_with_nameless_column
                    description: 이름 없는 열을 검증하는 모델
                    columns:
                      - description: 이름을 분류할 수 없는 열 설명
                """,
            )
            column_report = lint.lint_schema_contracts(
                [nameless_column], required_language="ko-KR"
            )
            self.assertEqual(
                1, column_report["summary"]["description_fields_unaccounted"]
            )
            self.assertLess(column_report["summary"]["coverage_percentage"], 100.0)
            self.assertEqual("FAIL", column_report["proof"]["source_yaml_uniqueness"])

            missing_selector = lint.lint_schema_contracts(
                [missing_description],
                resources=["not_declared"],
                required_language="ko-KR",
            )
            self.assertEqual(1, missing_selector["summary"]["resources_unaccounted"])
            self.assertEqual(
                1, missing_selector["summary"]["description_fields_unaccounted"]
            )
            self.assertLess(missing_selector["summary"]["coverage_percentage"], 100.0)

            nameless_resource = write_yaml(
                root,
                "nameless-resource.yml",
                """
                version: 2
                models:
                  - description: 이름을 분류할 수 없는 모델 설명
                """,
            )
            resource_report = lint.lint_schema_contracts(
                [nameless_resource], required_language="ko-KR"
            )
            self.assertEqual(1, resource_report["summary"]["resources_unaccounted"])
            self.assertEqual(
                1, resource_report["summary"]["description_fields_unaccounted"]
            )
            self.assertLess(resource_report["summary"]["coverage_percentage"], 100.0)
            self.assertEqual("FAIL", resource_report["proof"]["source_yaml_uniqueness"])

    def test_every_report_has_machine_readable_source_declaration_proof_boundaries(
        self,
    ) -> None:
        expected_limit = (
            "이 도구는 실제 relation 컬럼·타입·순서, SQL projection, grain, 최신 선택과 "
            "tie-break, reconciliation 또는 데이터 의미 정합성을 증명하지 않습니다."
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            valid = write_yaml(root, "valid.yml", VALID_MIXED_SCHEMA)
            invalid = write_yaml(
                root,
                "invalid.yml",
                """
                version: 2
                models:
                  - name: invalid_model
                    description: English only
                """,
            )
            reports = [
                (
                    lint.lint_schema_contracts([valid], required_language="ko-KR"),
                    "PASS",
                    "PASS",
                ),
                (
                    lint.lint_schema_contracts([invalid], required_language="ko-KR"),
                    "FAIL",
                    "PASS",
                ),
                (
                    lint.lint_schema_contracts(
                        [root / "missing"], required_language="ko-KR"
                    ),
                    "FAIL",
                    "FAIL",
                ),
            ]
            for report, declared, uniqueness in reports:
                with self.subTest(status=report["status"]):
                    self.assertEqual("source_yaml_declaration", report["proof_scope"])
                    self.assertEqual(expected_limit, report["claim_limitations_ko"])
                    self.assertEqual(
                        {
                            "data_contract": "NOT_RUN",
                            "declared_contract": declared,
                            "manual_semantic_review": "REQUIRED",
                            "physical_contract": "NOT_RUN",
                            "source_yaml_uniqueness": uniqueness,
                        },
                        report["proof"],
                    )


if __name__ == "__main__":
    unittest.main()
