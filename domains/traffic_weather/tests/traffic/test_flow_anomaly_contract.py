from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "traffic"
    / "transform"
    / "gold"
    / "gold_traffic_flow_anomaly_current.sql"
)


def _render_model() -> str:
    return Environment(autoescape=False).from_string(
        MODEL_PATH.read_text(encoding="utf-8")
    ).render(
        config=lambda **_: "",
        ref=lambda model_name: f"relation__{model_name}",
        asac_axes=SimpleNamespace(
            utc_to_kst=lambda expression: f"({expression} + interval '9' hour)"
        ),
    )


def test_anomaly_baseline_only_uses_observations_strictly_before_latest():
    rendered_sql = " ".join(_render_model().lower().split())

    assert (
        "and cast((flow.observed_at + interval '9' hour) as timestamp(6)) "
        "< latest.observed_at_kst"
    ) in rendered_sql
