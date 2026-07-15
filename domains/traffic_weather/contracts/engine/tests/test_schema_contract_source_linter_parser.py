from __future__ import annotations

from contracts.engine.tests.fixtures import (
    Path,
    lint,
    tempfile,
    textwrap,
    unittest,
    write_yaml,
)


class SchemaContractSourceLinterParserTests(unittest.TestCase):
    def test_yaml_node_properties_are_rejected_only_outside_quotes(self) -> None:
        unsupported = {
            "tag": "description: !custom 한국어 설명",
            "wide_anchor": "description: &shared.name 한국어 설명",
            "wide_alias": "description: *shared/path",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for name, construct in unsupported.items():
                with self.subTest(name=name):
                    path = write_yaml(
                        root,
                        f"{name}.yml",
                        f"""
                        version: 2
                        models:
                          - name: model_{name}
                            description: 정상 모델 설명
                            columns:
                              - name: value
                                {construct}
                        """,
                    )

                    report = lint.lint_schema_contracts(
                        [path], required_language="ko-KR"
                    )

                    self.assertEqual("FAIL", report["status"])
                    self.assertEqual("FAIL", report["files"][0]["scan_status"])
                    self.assertEqual(
                        ["UNSUPPORTED_YAML"],
                        [error["code"] for error in report["errors"]],
                    )

            quoted_path = write_yaml(
                root,
                "quoted-node-like-literals.yml",
                """
                version: 2
                models:
                  - name: quoted_node_literals
                    description: "서울 &source.name *literal/path !custom 문자 설명"
                    columns:
                      - name: literal_text
                        description: '서울 &single.anchor *single/alias !single 문자 설명'
                """,
            )
            quoted_report = lint.lint_schema_contracts(
                [quoted_path], required_language="ko-KR"
            )

            self.assertEqual("PASS", quoted_report["status"])
            self.assertEqual([], quoted_report["errors"])

    def test_invalid_plain_scalar_indicators_mapping_separators_and_controls_fail_closed(
        self,
    ) -> None:
        cases = {
            "at_indicator": "description: @later",
            "backtick_indicator": "description: `later`",
            "percent_indicator": "description: %later",
            "bad_literal_indicator": "description: |invalid",
            "bad_folded_indicator": "description: >invalid",
            "question_indicator": "description: ? later",
            "dash_indicator": "description: - later",
            "colon_indicator": "description: : later",
            "comma_indicator": "description: ,later",
            "nul_control": "description: 서울\x00설명",
            "c0_control": "description: 서울\x01설명",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for name, construct in cases.items():
                with self.subTest(name=name):
                    path = write_yaml(
                        root,
                        f"{name}.yml",
                        (
                            "version: 2\n"
                            "models:\n"
                            f"  - name: model_{name}\n"
                            "    description: 정상 모델 설명\n"
                            "    columns:\n"
                            "      - name: value\n"
                            f"        {construct}\n"
                        ),
                    )
                    report = lint.lint_schema_contracts(
                        [path], required_language="ko-KR"
                    )
                    self.assertEqual("FAIL", report["status"], report)
                    self.assertEqual("FAIL", report["files"][0]["scan_status"])
                    self.assertEqual(
                        ["UNSUPPORTED_YAML"],
                        [error["code"] for error in report["errors"]],
                    )

            no_space_fixtures = {
                "name": "version: 2\nmodels:\n  - name:model\n    description: 모델 설명\n",
                "description": "version: 2\nmodels:\n  - name: model\n    description:한국어 설명\n",
            }
            for name, body in no_space_fixtures.items():
                with self.subTest(no_space=name):
                    path = write_yaml(root, f"no-space-{name}.yml", body)
                    report = lint.lint_schema_contracts(
                        [path], required_language="ko-KR"
                    )
                    self.assertEqual("FAIL", report["status"], report)
                    self.assertEqual("FAIL", report["files"][0]["scan_status"])

    def test_yaml_double_quoted_x_n_and_json_escapes_decode_and_unknown_escape_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            valid = write_yaml(
                root,
                "yaml-escapes.yml",
                """
                version: 2
                models:
                  - name: escaped_model
                    description: "서울\\x20설명\\N다음 줄"
                    columns:
                      - name: escaped_column
                        description: "탭\\t설명과 유니코드 \\uC11C"
                """,
            )
            report = lint.lint_schema_contracts([valid], required_language="ko-KR")
            self.assertEqual("PASS", report["status"], report)
            values = [item["value"] for item in report["descriptions"]]
            self.assertIn("서울 설명\u0085다음 줄", values)
            self.assertIn("탭\t설명과 유니코드 서", values)

            invalid = write_yaml(
                root,
                "unknown-escape.yml",
                """
                version: 2
                models:
                  - name: unknown_escape
                    description: "서울\\q설명"
                """,
            )
            invalid_report = lint.lint_schema_contracts(
                [invalid], required_language="ko-KR"
            )
            self.assertEqual("FAIL", invalid_report["status"])
            self.assertEqual("FAIL", invalid_report["files"][0]["scan_status"])

    def test_yaml_double_quote_decoder_preserves_parity_and_validates_codepoints(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            valid_body = (
                "version: 2\nmodels:\n"
                "  - name: single_x\n" + r'    description: "서울\x20설명"' + "\n"
                "  - name: single_n\n" + r'    description: "서울\N설명"' + "\n"
                "  - name: double_x\n" + r'    description: "서울\\x20설명"' + "\n"
                "  - name: double_n\n" + r'    description: "서울\\N설명"' + "\n"
                "  - name: yaml_safe\n"
                + r'    description: "공백\_구분\L줄\P문단 \U0001F600\ 설명"'
                + "\n"
                "  - name: json_safe\n"
                + r'    description: "따옴표 \"서울\" 탭\t 개행\n 복귀\r 유니코드\uC11C 슬래시\/"'
                + "\n"
            )
            valid = write_yaml(root, "parity.yml", valid_body)
            report = lint.lint_schema_contracts([valid], required_language="ko-KR")
            self.assertEqual("PASS", report["status"], report)
            values = {
                item["resource_name"]: item["value"] for item in report["descriptions"]
            }
            self.assertEqual("서울 설명", values["single_x"])
            self.assertEqual("서울\u0085설명", values["single_n"])
            self.assertEqual(r"서울\x20설명", values["double_x"])
            self.assertEqual(r"서울\N설명", values["double_n"])
            self.assertEqual(
                "공백\u00a0구분\u2028줄\u2029문단 😀 설명", values["yaml_safe"]
            )
            self.assertEqual(
                '따옴표 "서울" 탭\t 개행\n 복귀\r 유니코드서 슬래시/',
                values["json_safe"],
            )

            invalid_escapes = {
                "unknown": r"\q",
                "short_x": r"\x2",
                "short_u": r"\u123",
                "out_of_range": r"\U00110000",
                "surrogate": r"\uD800",
                "forbidden_control": r"\x00",
                "backspace_control": r"\b",
                "formfeed_control": r"\f",
            }
            for name, escape in invalid_escapes.items():
                with self.subTest(name=name):
                    path = write_yaml(
                        root,
                        f"invalid-{name}.yml",
                        "version: 2\nmodels:\n"
                        f"  - name: invalid_{name}\n"
                        f'    description: "서울{escape}설명"\n',
                    )
                    invalid_report = lint.lint_schema_contracts(
                        [path], required_language="ko-KR"
                    )
                    self.assertEqual("FAIL", invalid_report["status"], invalid_report)
                    self.assertEqual("FAIL", invalid_report["files"][0]["scan_status"])

    def test_extra_plain_scalar_mapping_separator_fails_but_common_colons_pass(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            invalid_values = {
                "colon_space": "description: 서울: 설명",
                "colon_end": "description: 서울:",
                "name_extra": "name: model: extra",
            }
            for name, line in invalid_values.items():
                with self.subTest(name=name):
                    body = (
                        "version: 2\nmodels:\n"
                        f"  - {line if name == 'name_extra' else 'name: model_' + name}\n"
                    )
                    if name == "name_extra":
                        body += "    description: 정상 모델 설명\n"
                    else:
                        body += f"    {line}\n"
                    path = write_yaml(root, f"invalid-{name}.yml", body)
                    report = lint.lint_schema_contracts(
                        [path], required_language="ko-KR"
                    )
                    self.assertEqual("FAIL", report["status"], report)
                    self.assertEqual("FAIL", report["files"][0]["scan_status"])

            valid = write_yaml(
                root,
                "valid-colons.yml",
                """
                version: 2
                models:
                  - name: valid_colons
                    description: 서울 링크 https://example.com/data 시간 12:30 경로 /{mt10id}
                """,
            )
            valid_report = lint.lint_schema_contracts(
                [valid], required_language="ko-KR"
            )
            self.assertEqual("PASS", valid_report["status"], valid_report)

    def test_plain_scalar_mid_quotes_and_brackets_do_not_hide_mapping_separators(
        self,
    ) -> None:
        invalid_values = {
            "double_quote": '서울 "foo: bar" 설명',
            "single_quote": "서울 'foo: bar' 설명",
            "square": "서울 [foo: bar] 설명",
            "curly": "서울 {foo: bar} 설명",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for name, value in invalid_values.items():
                with self.subTest(name=name):
                    path = write_yaml(
                        root,
                        f"invalid-{name}.yml",
                        "version: 2\nmodels:\n"
                        f"  - name: invalid_{name}\n"
                        f"    description: {value}\n",
                    )
                    report = lint.lint_schema_contracts(
                        [path], required_language="ko-KR"
                    )
                    self.assertEqual("FAIL", report["status"], report)
                    self.assertEqual("FAIL", report["files"][0]["scan_status"])

            valid = write_yaml(
                root,
                "valid-embedded.yml",
                """
                version: 2
                models:
                  - name: valid_embedded
                    description: 서울 https://example.com 12:30 /{mt10id} "foo" [bar] {baz} 설명
                """,
            )
            valid_report = lint.lint_schema_contracts(
                [valid], required_language="ko-KR"
            )
            self.assertEqual("PASS", valid_report["status"], valid_report)

    def test_raw_c1_controls_fail_except_yaml_printable_nel(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for codepoint in (0x80, 0x86, 0x9F):
                with self.subTest(codepoint=hex(codepoint)):
                    path = write_yaml(
                        root,
                        f"c1-{codepoint:02x}.yml",
                        "version: 2\nmodels:\n"
                        f"  - name: c1_{codepoint:02x}\n"
                        f"    description: 서울{chr(codepoint)}설명\n",
                    )
                    report = lint.lint_schema_contracts(
                        [path], required_language="ko-KR"
                    )
                    self.assertEqual("FAIL", report["status"], report)
                    self.assertEqual("FAIL", report["files"][0]["scan_status"])

            nel = write_yaml(
                root,
                "nel.yml",
                "version: 2\nmodels:\n"
                "  - name: raw_nel\n"
                "    description: 서울\u0085설명\n"
                "  - name: escaped_nel\n" + r'    description: "서울\N설명"' + "\n",
            )
            report = lint.lint_schema_contracts([nel], required_language="ko-KR")
            self.assertEqual("PASS", report["status"], report)
            values = {
                item["resource_name"]: item["value"] for item in report["descriptions"]
            }
            self.assertEqual("서울\u0085설명", values["raw_nel"])
            self.assertEqual("서울\u0085설명", values["escaped_nel"])

    def test_implicit_nested_flow_reserved_closers_and_bad_block_indent_fail_closed(
        self,
    ) -> None:
        unsupported = {
            "implicit_flow_map": "values: [key: value]",
            "implicit_flow_sequence": "values: [- nested]",
            "implicit_flow_map_value": "freshness: {count: nested: value}",
            "implicit_flow_sequence_value": "freshness: {count: - nested}",
            "leading_square_closer": "description: ] 한국어 설명",
            "leading_curly_closer": "description: } 한국어 설명",
            "explicit_block_indent": "description: |4-\n  너무 얕은 블록 설명",
            "implicit_block_dedent": (
                "description: |\n    첫 번째 블록 설명\n  뒤에서 낮아진 블록 설명"
            ),
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for name, construct in unsupported.items():
                with self.subTest(name=name):
                    path = write_yaml(
                        root,
                        f"{name}.yml",
                        (
                            "version: 2\n"
                            "models:\n"
                            f"  - name: model_{name}\n"
                            "    description: 정상 모델 설명\n"
                            "    columns:\n"
                            "      - name: value\n"
                            "        description: 정상 열 설명\n"
                            f"{textwrap.indent(construct, '        ')}\n"
                        ),
                    )

                    report = lint.lint_schema_contracts(
                        [path], required_language="ko-KR"
                    )

                    self.assertEqual("FAIL", report["status"], report)
                    self.assertEqual("FAIL", report["files"][0]["scan_status"])
                    self.assertTrue(
                        any(
                            error["code"] == "UNSUPPORTED_YAML"
                            for error in report["errors"]
                        ),
                        report,
                    )


if __name__ == "__main__":
    unittest.main()
