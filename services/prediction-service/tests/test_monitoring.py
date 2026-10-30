import json
import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from prediction_service import monitoring
from prediction_service.monitoring import summarize

ROOT = Path(__file__).resolve().parents[3]
DASHBOARD = ROOT / "infra/monitoring/grafana/dashboards/overview.json"


def test_errors_use_the_training_nmae_and_a_signed_bias():
    # measured, champion only, published
    summary = summarize([(100.0, 130.0, 105.0), (50.0, 65.0, 45.0)])

    assert summary.hours == 2
    assert summary.champion_nmae_pct == pytest.approx(100 * (30 + 15) / 150)
    assert summary.published_nmae_pct == pytest.approx(100 * (5 + 5) / 150)
    assert summary.published_bias_pct == pytest.approx(0.0)


def test_no_summary_without_usable_hours():
    assert summarize([]) is None
    assert summarize([(0.0, 10.0, 10.0)]) is None


def test_one_line_per_site_on_the_last_24_closed_hours(monkeypatch, caplog):
    windows = []

    def errors(_url, start, end):
        windows.append((start, end))
        return [
            ("SITE002", 800.0, 1000.0, 820.0),
            ("SITE001", 170.0, 217.0, 171.0),
            ("SITE001", 62.0, 86.0, 63.0),
        ]

    monkeypatch.setattr(monitoring, "read_forecast_errors", errors)
    caplog.set_level(logging.INFO, logger="prediction_service.monitoring")

    monitoring.log_forecast_errors("db", datetime(2026, 10, 27, 14, 5, 30, tzinfo=UTC))

    end = datetime(2026, 10, 27, 14, tzinfo=UTC)
    assert windows == [(end - timedelta(hours=24), end)]
    assert [record.getMessage() for record in caplog.records] == [
        "Suivi modèle SITE001 : nMAE champion 30.6 %, publiée 0.9 %, biais publié +0.9 % (2 h)",
        "Suivi modèle SITE002 : nMAE champion 25.0 %, publiée 2.5 %, biais publié +2.5 % (1 h)",
    ]


def _dashboard_regexps(prefix: str) -> list[str]:
    dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    expressions = [
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
        if prefix in target.get("expr", "")
    ]
    return [re.search(r'regexp "((?:[^"\\]|\\.)*)"', expr).group(1) for expr in expressions]


@pytest.mark.skipif(not DASHBOARD.is_file(), reason="dashboard Grafana absent de cette copie")
def test_grafana_regexps_parse_the_logged_lines():
    """The dashboard reads these logs with LogQL regexps: they must stay aligned."""
    lines = {
        "Suivi modèle": "Suivi modèle SITE001 : nMAE champion 30.6 %, publiée 0.9 %, "
        "biais publié -0.9 % (24 h)",
        "Recalage": "Recalage SITE004 : 0.765 (heures travaillées 0.701, autres 1.018, "
        "168 h mesurées)",
    }
    for prefix, line in lines.items():
        regexps = _dashboard_regexps(prefix)
        assert regexps, f"aucune requête du dashboard ne lit « {prefix} »"
        for pattern in regexps:
            # JSON then LogQL escape backslashes: \\d in the file becomes \d.
            match = re.search(pattern.replace("\\\\", "\\"), line)
            assert match, pattern
            assert match.group("site") in {"SITE001", "SITE004"}
