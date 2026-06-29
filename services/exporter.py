# services/exporter.py
from __future__ import annotations

import json
from pathlib import Path


def save_json(path: Path, data) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(path)


def save_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def export_all(
    run_paths: dict,
    report_markdown: str,
    evidence_pack: list[dict],
    impact_assessments: list[dict],
) -> dict[str, str]:
    report_path = run_paths["reports"] / "report.md"
    evidence_path = run_paths["reports"] / "evidence.json"
    assessment_path = run_paths["reports"] / "impact_assessments.json"

    return {
        "report": save_text(report_path, report_markdown),
        "evidence": save_json(evidence_path, evidence_pack),
        "assessments": save_json(assessment_path, impact_assessments),
    }