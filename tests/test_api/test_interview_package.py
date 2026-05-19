from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = PROJECT_ROOT / "docs" / "interview-package"


def test_interview_package_contains_required_documents():
    expected_files = {
        "README.md",
        "architecture.md",
        "api-walkthrough.md",
        "runbook.md",
        "tradeoffs.md",
    }

    assert expected_files.issubset({path.name for path in PACKAGE_DIR.iterdir()})


def test_architecture_doc_contains_required_production_concepts():
    architecture = (PACKAGE_DIR / "architecture.md").read_text(encoding="utf-8")

    assert "workflow-first" in architecture
    assert "Temporal" in architecture
    assert "LiteLLM" in architecture
    assert "Postgres" in architecture
    assert "mermaid" in architecture
    assert "Production Gaps" in architecture


def test_runbook_documents_operational_commands():
    runbook = (PACKAGE_DIR / "runbook.md").read_text(encoding="utf-8")

    assert "docker compose up --build" in runbook
    assert "python -m app.temporal.worker" in runbook
    assert "python -m pytest" in runbook
    assert "python -m app.evals.run_evals" in runbook


def test_api_walkthrough_documents_core_demo_endpoints():
    walkthrough = (PACKAGE_DIR / "api-walkthrough.md").read_text(encoding="utf-8")

    assert "/workflows/daily-ops/run" in walkthrough
    assert "/workflows/daily-ops/temporal/start" in walkthrough
    assert "/approvals" in walkthrough
    assert "/observability/audit-logs" in walkthrough
