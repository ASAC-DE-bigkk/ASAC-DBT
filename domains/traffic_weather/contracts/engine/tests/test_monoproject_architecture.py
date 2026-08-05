from __future__ import annotations

import configparser
from pathlib import Path

import yaml
from yaml.tokens import AliasToken, AnchorToken


def _find_repository_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists() and (candidate / "domains").is_dir():
            return candidate
    raise RuntimeError("ASAC-DBT repository root could not be located")


REPOSITORY_ROOT = _find_repository_root(Path(__file__).resolve())
PROJECT_ROOT = REPOSITORY_ROOT / "domains" / "traffic_weather"
DOMAINS = ("traffic", "weather")
MAX_PROJECT_AI_INDEX_LINES = 100
PROJECT_AI_INDEX_TOKENS = {
    "Traffic/Weather monoproject",
    "dbt_project.yml",
    "selectors.yml",
    "workflows/premerge_gate.py",
    "models/traffic/README.md",
    "models/weather/README.md",
    "contracts/engine/README.md",
    "../../packages/asac_axes",
    "access: public",
    "ref('asac_seoul'",
    "tags/selectors",
    "dbt deps",
    "dbt parse",
    "traffic_snapshot_dag_run_id",
}


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _domain_yaml_paths(domain: str, project_root: Path = PROJECT_ROOT) -> list[Path]:
    roots = (project_root / "models" / domain, project_root / "seeds" / domain)
    return sorted(
        path for root in roots if root.exists() for path in root.rglob("*.yml")
    )


def _domain_resources(domain: str, project_root: Path = PROJECT_ROOT):
    for path in _domain_yaml_paths(domain, project_root):
        document = _yaml(path)
        if not isinstance(document, dict):
            continue
        for resource_type in ("models", "seeds"):
            for resource in document.get(resource_type, []):
                yield path, resource_type, resource


def _paths_to_tag(value, tag: str, path: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    matches: set[tuple[str, ...]] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = (*path, str(key))
            if key == "+tags" and isinstance(child, list) and tag in child:
                matches.add(child_path)
            matches.update(_paths_to_tag(child, tag, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            matches.update(_paths_to_tag(child, tag, (*path, str(index))))
    return matches


def _tag_values(value) -> set[str]:
    tags: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"+tags", "tags"} and isinstance(child, list):
                tags.update(tag for tag in child if isinstance(tag, str))
            tags.update(_tag_values(child))
    elif isinstance(value, list):
        for child in value:
            tags.update(_tag_values(child))
    return tags


def test_traffic_weather_share_one_domain_owned_dbt_project() -> None:
    project_path = PROJECT_ROOT / "dbt_project.yml"
    profile_path = PROJECT_ROOT / "profiles.yml"

    assert project_path.is_file()
    assert profile_path.is_file()
    assert _yaml(project_path)["name"] == "asac_seoul"
    assert _yaml(project_path)["profile"] == "asac_seoul"
    assert set(_yaml(profile_path)) == {"asac_seoul"}

    legacy = [
        REPOSITORY_ROOT / "domains" / domain / filename
        for domain in DOMAINS
        for filename in (
            "dbt_project.yml",
            "profiles.yml",
            "packages.yml",
            "package-lock.yml",
        )
        if (REPOSITORY_ROOT / "domains" / domain / filename).exists()
    ]
    assert not legacy
    assert not (REPOSITORY_ROOT / "dbt_project.yml").exists()
    assert not (REPOSITORY_ROOT / "selectors.yml").exists()


def test_project_has_a_concise_monoproject_ai_index() -> None:
    readme_path = PROJECT_ROOT / "README.md"

    assert readme_path.is_file()
    readme = readme_path.read_text(encoding="utf-8")
    assert len(readme.splitlines()) <= MAX_PROJECT_AI_INDEX_LINES
    missing_tokens = {token for token in PROJECT_AI_INDEX_TOKENS if token not in readme}
    assert not missing_tokens


def test_project_graph_uses_conventional_domain_paths() -> None:
    expected = (
        PROJECT_ROOT / "models" / "traffic" / "sources.yml",
        PROJECT_ROOT / "models" / "weather" / "sources.yml",
        PROJECT_ROOT / "tests" / "traffic" / "__init__.py",
        PROJECT_ROOT / "tests" / "weather" / "__init__.py",
        PROJECT_ROOT / "macros" / "weather",
        PROJECT_ROOT / "seeds" / "weather",
        PROJECT_ROOT / "models" / "groups.yml",
        PROJECT_ROOT / "macros" / "generate_schema_name.sql",
        PROJECT_ROOT / "selectors.yml",
        PROJECT_ROOT / "analyses" / "traffic_weather",
    )

    assert all(path.exists() for path in expected)
    assert (PROJECT_ROOT / "tests" / "__init__.py").is_file()


def test_generated_artifact_ignores_are_narrow_and_cross_platform() -> None:
    rules = {
        line.strip()
        for line in (REPOSITORY_ROOT / ".gitignore")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert {"__pycache__/", "*.py[cod]", ".pytest_cache/"} <= rules
    assert {"/target/", "/logs/", "/dbt_packages/"} <= rules
    assert {
        "/domains/traffic_weather/target/",
        "/domains/traffic_weather/logs/",
        "/domains/traffic_weather/dbt_packages/",
    } <= rules
    assert not {"**/target/", "**/logs/", "**/dbt_packages/"} & rules


def test_project_pytest_config_owns_suites_and_ignores_generated_trees() -> None:
    config = configparser.ConfigParser()
    loaded = config.read(PROJECT_ROOT / "pytest.ini", encoding="utf-8")

    assert loaded
    assert config["pytest"]["pythonpath"].split() == ["../.."]
    testpaths = set(config["pytest"]["testpaths"].split())
    assert testpaths == {
        "workflows/tests",
        "contracts/engine/tests",
        "contracts/traffic/tests",
        "tests/traffic", "tests/weather", "tests/test_d1_public_serving_products.py",
    }
    ignored = set(config["pytest"]["norecursedirs"].split())
    assert {".git", "dbt_packages", "target", "logs"} <= ignored


def test_phase_membership_is_owned_by_folders_not_resource_name_lists() -> None:
    project = _yaml(PROJECT_ROOT / "dbt_project.yml")
    serialized = (PROJECT_ROOT / "dbt_project.yml").read_text(encoding="utf-8")

    assert "ask_seoul_traffic_transform_silver" in serialized
    assert "ask_seoul_traffic_transform_gold" in serialized
    assert "ask_seoul_weather_transform_silver" in serialized
    assert "ask_seoul_weather_transform_gold" in serialized
    assert "ask_seoul_weather_transform_place_mart" in serialized
    assert "gold_traffic_incident_summary:" not in serialized
    assert "assert_gold_weather_counts_match_silver:" not in serialized
    assert project["model-paths"] == ["models"]
    assert project["test-paths"] == ["tests"]


def test_every_execution_tag_has_one_described_named_selector() -> None:
    selectors = _yaml(PROJECT_ROOT / "selectors.yml")["selectors"]
    names = [selector["name"] for selector in selectors]
    configured_tags = _tag_values(_yaml(PROJECT_ROOT / "dbt_project.yml"))
    for domain in DOMAINS:
        for properties_path in _domain_yaml_paths(domain):
            configured_tags.update(_tag_values(_yaml(properties_path)))
    execution_tags = {
        tag
        for tag in configured_tags
        if tag.startswith(("ask_seoul_traffic_", "ask_seoul_weather_"))
    }

    assert len(names) == len(set(names))
    assert execution_tags <= set(names)
    by_name = {selector["name"]: selector for selector in selectors}
    for tag in execution_tags:
        assert by_name[tag]["description"].strip()
        assert by_name[tag]["definition"] == {
            "method": "tag",
            "value": tag,
            "indirect_selection": "cautious",
        }


def test_source_contract_gates_are_manifest_owned_intersections() -> None:
    selectors = _yaml(PROJECT_ROOT / "selectors.yml")["selectors"]
    by_name = {selector["name"]: selector for selector in selectors}

    for domain in DOMAINS:
        selector = by_name[f"{domain}_transform_contract_gate"]
        assert selector["description"].strip()
        assert selector["definition"] == {
            "intersection": [
                {
                    "method": "tag",
                    "value": f"ask_seoul_{domain}_transform_source",
                    "indirect_selection": "cautious",
                },
                {"method": "test_type", "value": "generic"},
            ]
        }


def test_crosswalk_builder_receives_consumer_inputs_through_its_cli() -> None:
    script_path = (
        REPOSITORY_ROOT
        / "packages"
        / "asac_axes"
        / "scripts"
        / "build_crosswalk.py"
    )
    script = script_path.read_text(encoding="utf-8")
    assert "domains/traffic_weather" not in script
    assert "domains/population" not in script
    assert "REPO =" not in script
    for option in (
        "--weather-grid",
        "--dong-boundary",
        "--gu-boundary",
        "--output-dir",
    ):
        assert option in script


def test_cross_domain_analysis_is_a_read_only_hour_context_recipe() -> None:
    analysis = (
        PROJECT_ROOT / "analyses" / "traffic_weather" / "admin_dong_hour_context.sql"
    )

    assert analysis.is_file()
    sql = analysis.read_text(encoding="utf-8")
    assert (
        "ref('asac_seoul', 'gold_traffic_incident_current_by_admin_dong_hourly')" in sql
    )
    assert "ref('asac_seoul', 'gold_weather_forecast_by_admin_dong')" in sql
    assert "admin_dong_code" in sql
    assert "admin_dong_revision_date" in sql
    assert "forecast_at >= traffic_hour.hour_at" in sql
    assert "forecast_at < traffic_hour.hour_at + interval '1' hour" in sql
    assert "quality_state in ('complete', 'complete_zero')" in sql
    assert "date_trunc('hour'" not in sql
    assert "materialized" not in sql.lower()


def test_split_schema_declares_each_discovered_resource_exactly_once() -> None:
    duplicates: list[tuple[str, str, str]] = []

    for domain in DOMAINS:
        actual = {"models": set(), "seeds": set()}
        for _, resource_type, resource in _domain_resources(domain):
            key = (domain, resource_type, resource["name"])
            if resource["name"] in actual[resource_type]:
                duplicates.append(key)
            actual[resource_type].add(resource["name"])

        assert actual["models"], domain
        if domain == "weather":
            assert actual["seeds"]

    assert duplicates == []


def test_resource_discovery_accepts_a_new_colocated_model_without_a_registry(
    tmp_path: Path,
) -> None:
    model_dir = tmp_path / "models" / "traffic" / "transform" / "silver"
    model_dir.mkdir(parents=True)
    (model_dir / "new_tagged_model.sql").write_text("select 1", encoding="utf-8")
    (model_dir / "_silver.yml").write_text(
        "version: 2\nmodels:\n  - name: new_tagged_model\n",
        encoding="utf-8",
    )

    discovered = list(_domain_resources("traffic", tmp_path))

    assert [(kind, resource["name"]) for _, kind, resource in discovered] == [
        ("models", "new_tagged_model")
    ]


def test_model_properties_are_colocated_and_public_gold_is_one_to_one() -> None:
    for domain in DOMAINS:
        assert not (PROJECT_ROOT / "models" / domain / "schema.yml").exists()
        for yaml_path in _domain_yaml_paths(domain):
            if yaml_path.name == "sources.yml" or "seeds" in yaml_path.parts:
                continue
            for token in yaml.scan(yaml_path.read_text(encoding="utf-8")):
                assert not isinstance(token, (AnchorToken, AliasToken))

        for properties_path, resource_type, model in _domain_resources(domain):
            if resource_type != "models":
                continue
            sql_matches = list(
                (PROJECT_ROOT / "models" / domain).rglob(f"{model['name']}.sql")
            )
            assert len(sql_matches) == 1, model["name"]
            assert properties_path.parent == sql_matches[0].parent

    public_properties = {
        PROJECT_ROOT
        / "models"
        / "traffic"
        / "transform"
        / "gold"
        / "gold_traffic_incident_current_by_admin_dong_hourly.yml": "gold_traffic_incident_current_by_admin_dong_hourly",
        PROJECT_ROOT
        / "models"
        / "weather"
        / "special"
        / "gold"
        / "gold_weather_forecast_by_admin_dong.yml": "gold_weather_forecast_by_admin_dong",
    }
    for path, model_name in public_properties.items():
        assert path.is_file()
        assert [model["name"] for model in _yaml(path)["models"]] == [model_name]


def test_domain_readmes_are_short_ai_indexes() -> None:
    required = {
        "traffic": (
            "ask_seoul_traffic_transform_silver",
            "ask_seoul_traffic_transform_gold",
            "ask_seoul_traffic_recovery_silver",
            "gold_traffic_incident_current_by_admin_dong_hourly",
            "published_producer",
            "normal",
            "recovery",
            "cross-domain ref",
            "ref('asac_seoul',",
        ),
        "weather": (
            "ask_seoul_weather_transform_silver",
            "ask_seoul_weather_w1_bridge",
            "ask_seoul_weather_w1_inputs",
            "gold_weather_forecast_by_admin_dong",
            "published_producer",
            "normal",
            "special",
            "cross-domain ref",
            "ref('asac_seoul',",
        ),
    }
    for domain, tokens in required.items():
        readme_path = PROJECT_ROOT / "models" / domain / "README.md"
        assert readme_path.is_file()
        readme = readme_path.read_text(encoding="utf-8")
        assert len(readme.splitlines()) <= 100
        for token in tokens:
            assert token in readme


def test_weather_w1_tags_have_exact_direct_membership() -> None:
    project = _yaml(PROJECT_ROOT / "dbt_project.yml")
    bridge_tag = "ask_seoul_weather_w1_bridge"
    inputs_tag = "ask_seoul_weather_w1_inputs"

    assert _paths_to_tag(project, bridge_tag) == {
        ("models", "asac_seoul", "weather", "special", "w1", "+tags"),
        ("data_tests", "asac_seoul", "weather", "special", "w1", "+tags"),
    }
    assert _paths_to_tag(project, inputs_tag) == {
        ("seeds", "asac_seoul", "weather", "weather_place_grid_mapping", "+tags"),
        (
            "seeds",
            "asac_seoul",
            "weather",
            "weather_admin_dong_grid_bridge_history",
            "+tags",
        ),
        ("seeds", "asac_axes", "+tags"),
    }

    w1_models = {
        path.name
        for path in (PROJECT_ROOT / "models" / "weather" / "special" / "w1").glob("*.sql")
    }
    assert w1_models == {"bridge_weather_admin_dong_grid.sql"}

    w1_tests = {
        path.name
        for path in (PROJECT_ROOT / "tests" / "weather" / "special" / "w1").glob("*.sql")
    }
    assert w1_tests == {
        "assert_weather_bridge_candidate_grain_unique.sql",
        "assert_weather_bridge_canonical_stamp_exact.sql",
        "assert_weather_bridge_legacy_mapping_reconciles.sql",
        "assert_weather_bridge_temporal_evidence.sql",
        "assert_weather_bridge_validity_non_overlapping.sql",
    }

    axes_seed_names = {
        seed["name"]
        for seed in _yaml(
            REPOSITORY_ROOT
            / "packages"
            / "asac_axes"
            / "seeds"
            / "_asac_axes__seeds.yml"
        )["seeds"]
    }
    assert axes_seed_names == {
        "seoul_admin_dong_crosswalk",
        "seoul_admin_dong_boundary",
        "seoul_gu_boundary",
    }


def test_contract_docs_lint_the_colocated_public_gold_yaml() -> None:
    expected = {
        "traffic": (
            "models/traffic/transform/gold/gold_traffic_incident_current_by_admin_dong_hourly.yml",
            "models/traffic/sources.yml",
            "gold_traffic_incident_current_by_admin_dong_hourly",
        ),
        "weather": (
            "models/weather/special/gold/gold_weather_forecast_by_admin_dong.yml",
            "models/weather/sources.yml",
            "gold_weather_forecast_by_admin_dong",
        ),
    }
    for domain, (schema_root, sources_root, resource) in expected.items():
        contract = (
            PROJECT_ROOT
            / "contracts"
            / domain
            / "docs"
            / "public-gold-ai-contract-v1.md"
        ).read_text(encoding="utf-8")
        assert f"--schema-root {schema_root}" in contract
        assert f"--schema-root {sources_root}" in contract
        assert contract.count(f"--resource {resource}") >= 3
        assert f"domains/{domain}/models/" not in contract


def test_domain_operating_docs_use_project_paths_and_commands() -> None:
    for domain in DOMAINS:
        guide = (
            PROJECT_ROOT / "docs" / domain / "dbt_contracts.md"
        ).read_text(encoding="utf-8")

        assert f"models/{domain}" in guide
        assert f"tests/{domain}" in guide
        assert "dbt deps --project-dir . --profiles-dir ." in guide
        assert f"domains/{domain}/models/" not in guide
        assert f"--project-dir domains/{domain}" not in guide


def test_canonical_gold_plan_uses_only_current_monoproject_paths_and_node_ids() -> None:
    plan = (
        PROJECT_ROOT
        / "docs"
        / "traffic"
        / "superpowers"
        / "plans"
        / "2026-07-14-traffic-canonical-gold.md"
    ).read_text(encoding="utf-8")

    for stale in (
        "domains/traffic/models/",
        "domains/traffic/tests/",
        "python contracts/scripts/validate_singular_test_dependency_manifest.py",
        "model.traffic.",
    ):
        assert stale not in plan
    assert "models/traffic/" in plan
    assert "tests/traffic/" in plan
    assert "model.asac_seoul." in plan
