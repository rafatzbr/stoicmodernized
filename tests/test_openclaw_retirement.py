from pathlib import Path


def test_active_pipeline_has_no_openclaw_dependency():
    root = Path(__file__).resolve().parent.parent
    active_files = [root / "run_pouncing_paws.py", *sorted((root / "src").rglob("*.py"))]
    offenders = []
    for path in active_files:
        text = path.read_text(encoding="utf-8")
        if ".openclaw" in text or "openclaw" in text.lower():
            offenders.append(str(path.relative_to(root)))
    assert offenders == []


def test_migrated_pipeline_helpers_exist_outside_openclaw():
    scripts = Path.home() / ".hermes" / "scripts" / "content-pipeline"
    for name in ("whiskers_research.py", "mittens_script_reviewer.py"):
        path = scripts / name
        assert path.is_file()
        assert ".openclaw" not in path.read_text(encoding="utf-8")
