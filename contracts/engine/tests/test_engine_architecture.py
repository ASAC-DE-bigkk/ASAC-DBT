from __future__ import annotations

import ast
import importlib
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
ENGINE_ROOT = REPO_ROOT / "contracts" / "engine"
SHARED_MODULES = (
    "artifact_io.py",
    "lint_schema_contract_source.py",
    "validate_public_gold_manifest.py",
    "compare_public_gold_catalog.py",
)
SYMLINK_TEST_METHODS = {
    "test_schema_root_and_discovered_symlinks_are_rejected",
    "test_output_rejects_input_collision_and_symlink_without_modifying_targets",
    "test_output_collision_preflight_uses_raw_roots_before_early_error_reports",
    "test_every_raw_root_path_is_collision_protected_before_suffix_or_existence_validation",
    "test_canonicalized_output_parent_symlink_is_allowed_but_leaf_symlink_remains_blocked",
    "test_output_inside_raw_directory_is_blocked_lexically_and_canonically",
    "test_descendant_symlink_targets_are_protected_regardless_of_suffix_or_existence",
    "test_output_is_atomic_and_cannot_alias_either_input",
    "test_symlink_inputs_are_rejected_without_creating_output",
}
SPLIT_TEST_MODULES = {
    "test_cli_encoding.py": ("ContractCliUtf8StdoutTests", 2),
    "test_schema_contract_source_linter_semantics.py": (
        "SchemaContractSourceLinterSemanticTests",
        8,
    ),
    "test_schema_contract_source_linter_resources.py": (
        "SchemaContractSourceLinterResourceTests",
        7,
    ),
    "test_schema_contract_source_linter_parser.py": (
        "SchemaContractSourceLinterParserTests",
        8,
    ),
    "test_schema_contract_source_linter_filesystem.py": (
        "SchemaContractSourceLinterFilesystemTests",
        8,
    ),
    "test_public_gold_manifest_core.py": ("PublicGoldManifestCoreTests", 11),
    "test_public_gold_manifest_safety.py": ("PublicGoldManifestSafetyTests", 12),
    "test_public_gold_manifest_publication.py": (
        "PublicGoldManifestPublicationTests",
        10,
    ),
    "test_public_gold_manifest_exposure_timestamp.py": (
        "PublicGoldManifestExposureTimestampTests",
        1,
    ),
    "test_public_gold_manifest_semantics.py": (
        "PublicGoldManifestSemanticRuleTests",
        6,
    ),
    "test_public_gold_manifest_quality_lineage.py": (
        "PublicGoldManifestQualityLineageTests",
        2,
    ),
    "test_public_gold_catalog_validation.py": (
        "PublicGoldCatalogValidationTests",
        6,
    ),
    "test_public_gold_catalog_evidence.py": ("PublicGoldCatalogEvidenceTests", 5),
    "test_public_gold_catalog_io.py": ("PublicGoldCatalogIoTests", 5),
}
RETIRED_GIANT_TEST_MODULES = {
    "test_validate_public_gold_manifest.py",
    "test_schema_contract_source_linter.py",
    "test_public_gold_manifest.py",
    "test_public_gold_catalog_comparator.py",
}
CANONICAL_TESTS = tuple(
    ENGINE_ROOT / "tests" / filename for filename in SPLIT_TEST_MODULES
)
MAX_FACADE_LINES = 160
MAX_INTERNAL_LINES = 500
MAX_TEST_MODULE_LINES = 500
MAX_AI_INDEX_LINES = 100
ENGINE_AI_INDEX_TOKENS = {
    "lint_schema_contract_source.py",
    "validate_public_gold_manifest.py",
    "compare_public_gold_catalog.py",
    "_schema_contract",
    "_manifest_contract",
    "_catalog_contract",
    "artifact_io.py",
    "0 / 1 / 2",
    "stdout",
    "stderr",
    "UTF-8",
    "contracts/engine/tests",
}
ENGINE_PACKAGES = {
    "_schema_contract": {
        "__init__.py",
        "types.py",
        "lexing.py",
        "parsing.py",
        "descriptions.py",
        "resources.py",
        "reporting.py",
        "repository.py",
        "service.py",
        "cli.py",
    },
    "_manifest_contract": {
        "__init__.py",
        "foundation.py",
        "metadata.py",
        "publication.py",
        "time_rules.py",
        "space_rules.py",
        "semantic_rules.py",
        "lineage_rules.py",
        "node_validation.py",
        "service.py",
        "cli.py",
    },
    "_catalog_contract": {
        "__init__.py",
        "reporting.py",
        "parsing.py",
        "comparison.py",
        "cli.py",
    },
}
FACADE_EXPORTS = {
    "lint_schema_contract_source.py": {
        "MAX_FILE_BYTES",
        "MAX_LINE_COUNT",
        "MAX_LINE_LENGTH",
        "MAX_NESTING_DEPTH",
        "MAX_SCALAR_LENGTH",
        "lint_schema_contracts",
        "render_report",
        "main",
    },
    "validate_public_gold_manifest.py": {
        "MAX_JSON_CONTAINERS",
        "validate_manifest",
        "render_json",
        "main",
    },
    "compare_public_gold_catalog.py": {
        "compare_public_gold_catalog",
        "render_json",
        "main",
    },
}
FACADE_MODULES = {
    "lint_schema_contract_source.py": "contracts.engine.lint_schema_contract_source",
    "validate_public_gold_manifest.py": "contracts.engine.validate_public_gold_manifest",
    "compare_public_gold_catalog.py": "contracts.engine.compare_public_gold_catalog",
}


def _legacy_script(domain: str, filename: str) -> Path:
    return REPO_ROOT / "domains" / domain / "contracts" / "scripts" / filename


def test_public_gold_contract_implementation_has_one_root_engine() -> None:
    missing = [name for name in SHARED_MODULES if not (ENGINE_ROOT / name).is_file()]
    legacy = [
        path.relative_to(REPO_ROOT).as_posix()
        for domain in ("traffic", "weather")
        for name in SHARED_MODULES
        if (path := _legacy_script(domain, name)).exists()
    ]

    assert not missing, f"canonical engine modules are missing: {missing}"
    assert not legacy, f"domain-local copies remain: {legacy}"


def test_contract_engine_is_an_explicit_importable_package() -> None:
    package_markers = (
        REPO_ROOT / "contracts" / "__init__.py",
        ENGINE_ROOT / "__init__.py",
        ENGINE_ROOT / "tests" / "__init__.py",
    )

    assert all(path.is_file() for path in package_markers)


def test_contract_engine_has_a_concise_ai_index() -> None:
    readme_path = ENGINE_ROOT / "README.md"

    assert readme_path.is_file()
    readme = readme_path.read_text(encoding="utf-8")
    assert len(readme.splitlines()) <= MAX_AI_INDEX_LINES
    missing_tokens = {token for token in ENGINE_AI_INDEX_TOKENS if token not in readme}
    assert not missing_tokens


def test_contract_engine_private_packages_have_exact_responsibility_modules() -> None:
    for package_name, expected_files in ENGINE_PACKAGES.items():
        package_root = ENGINE_ROOT / package_name
        actual_files = {path.name for path in package_root.glob("*.py")}

        assert actual_files == expected_files, package_name
        assert not (package_root / "__init__.py").read_text(encoding="utf-8").strip()


def test_contract_engine_facades_and_internal_modules_stay_small() -> None:
    for filename in FACADE_EXPORTS:
        line_count = len(
            (ENGINE_ROOT / filename).read_text(encoding="utf-8").splitlines()
        )
        assert line_count <= MAX_FACADE_LINES, (filename, line_count)

    for package_name in ENGINE_PACKAGES:
        for path in (ENGINE_ROOT / package_name).glob("*.py"):
            line_count = len(path.read_text(encoding="utf-8").splitlines())
            assert line_count <= MAX_INTERNAL_LINES, (path.name, line_count)


def test_contract_engine_test_modules_stay_within_ai_context_budget() -> None:
    for path in (ENGINE_ROOT / "tests").glob("*.py"):
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        assert line_count <= MAX_TEST_MODULE_LINES, (path.name, line_count)


def test_contract_engine_facades_explicitly_reexport_only_compatibility_surface() -> (
    None
):
    for filename, expected_exports in FACADE_EXPORTS.items():
        path = ENGINE_ROOT / filename
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported_from_private = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module is not None
            and "_contract" in node.module
            for alias in node.names
        }

        assert "*" not in {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        assert imported_from_private == expected_exports, filename

        module = importlib.import_module(FACADE_MODULES[filename])
        assert all(hasattr(module, name) for name in expected_exports)


def test_contract_engine_private_imports_are_acyclic_and_bypass_facades() -> None:
    forbidden_facades = {
        "lint_schema_contract_source",
        "validate_public_gold_manifest",
        "compare_public_gold_catalog",
    }
    forbidden_downstream = {
        "_schema_contract": {"_manifest_contract", "_catalog_contract"},
        "_manifest_contract": {"_catalog_contract"},
        "_catalog_contract": set(),
    }

    for package_name in ENGINE_PACKAGES:
        for path in (ENGINE_ROOT / package_name).glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported_modules = {
                node.module or ""
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
            } | {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            }

            assert not {
                facade
                for facade in forbidden_facades
                if any(module.endswith(facade) for module in imported_modules)
            }, path
            assert not {
                downstream
                for downstream in forbidden_downstream[package_name]
                if any(downstream in module for module in imported_modules)
            }, path


def test_public_gold_contract_behavior_has_one_canonical_test_suite() -> None:
    legacy = [
        REPO_ROOT
        / "domains"
        / domain
        / "contracts"
        / "tests"
        / "test_validate_public_gold_manifest.py"
        for domain in ("traffic", "weather")
    ]

    assert all(path.is_file() for path in CANONICAL_TESTS)
    assert (ENGINE_ROOT / "tests" / "fixtures.py").is_file()
    assert not [path for path in legacy if path.exists()]


def test_public_gold_contract_tests_are_split_by_responsibility() -> None:
    tests_root = ENGINE_ROOT / "tests"
    assert (tests_root / "fixtures.py").is_file()
    assert (tests_root / "cli_fixtures.py").is_file()
    assert not [
        filename
        for filename in RETIRED_GIANT_TEST_MODULES
        if (tests_root / filename).exists()
    ]

    collected_test_count = 0
    for filename, (expected_class, expected_count) in SPLIT_TEST_MODULES.items():
        path = tests_root / filename
        assert path.is_file(), path
        tree = ast.parse(path.read_text(encoding="utf-8"))
        classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
        assert [node.name for node in classes] == [expected_class]
        test_count = sum(
            1
            for node in classes[0].body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        )
        assert test_count == expected_count
        collected_test_count += test_count

    assert collected_test_count == 91


def test_only_symlink_dependent_tests_use_the_capability_guard() -> None:
    guarded: set[str] = set()
    symlink_users: set[str] = set()

    for test_path in CANONICAL_TESTS:
        tree = ast.parse(test_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if any(
                isinstance(decorator, ast.Name)
                and decorator.id == "requires_symlink_capability"
                for decorator in node.decorator_list
            ):
                guarded.add(node.name)
            if any(
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "symlink_to"
                for call in ast.walk(node)
            ):
                symlink_users.add(node.name)

    assert symlink_users == SYMLINK_TEST_METHODS
    assert guarded == SYMLINK_TEST_METHODS


def test_traffic_public_gold_uses_the_canonical_approved_revision() -> None:
    schema_path = (
        REPO_ROOT
        / "models"
        / "traffic"
        / "transform"
        / "gold"
        / "gold_traffic_incident_current_by_admin_dong_hourly.yml"
    )
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    model = next(
        item
        for item in schema["models"]
        if item["name"] == "gold_traffic_incident_current_by_admin_dong_hourly"
    )

    public_gold = model["config"]["meta"]["public_gold"]
    assert public_gold["space"]["approved_revision_date"] == "2025-04-01"


def test_canonical_traffic_and_weather_gold_models_are_public() -> None:
    canonical_models = {
        REPO_ROOT
        / "models"
        / "traffic"
        / "transform"
        / "gold"
        / "gold_traffic_incident_current_by_admin_dong_hourly.yml": "gold_traffic_incident_current_by_admin_dong_hourly",
        REPO_ROOT
        / "models"
        / "weather"
        / "special"
        / "gold"
        / "gold_weather_forecast_by_admin_dong.yml": "gold_weather_forecast_by_admin_dong",
    }

    for schema_path, model_name in canonical_models.items():
        schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        model = next(item for item in schema["models"] if item["name"] == model_name)

        assert model.get("access") == "public", f"{model_name} must be public"


def test_monoproject_ci_scope_tracks_both_domains_and_shared_contract_engine() -> None:
    workflow_path = (
        REPO_ROOT
        / ".github"
        / "workflows"
        / "traffic-weather-monoproject-premerge-gate.yml"
    )
    workflow = workflow_path.read_text(encoding="utf-8")

    assert "contracts/engine/" in workflow
    assert "domains/traffic/" in workflow
    assert "domains/weather/" in workflow


def test_contract_engine_does_not_mask_missing_internal_dependencies() -> None:
    engine_root = REPO_ROOT / "contracts" / "engine"
    offenders = []
    for path in engine_root.rglob("*.py"):
        if "tests" in path.parts:
            continue
        if "except ModuleNotFoundError" in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(REPO_ROOT).as_posix())

    assert offenders == []
