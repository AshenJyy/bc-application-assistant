import hashlib
import re
import zipfile
from pathlib import Path

from bc_application.preflight import check_environment

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/bc-application"


def test_all_bundled_wheels_are_locked_and_include_distribution_metadata():
    lines = (SKILL / "runtime-requirements.txt").read_text().splitlines()
    hashes = {line.split("--hash=sha256:")[1] for line in lines if "--hash=" in line}
    wheels = list((SKILL / "assets/wheels").glob("*.whl"))
    assert len(wheels) == len(hashes) == 8
    for wheel in wheels:
        assert hashlib.sha256(wheel.read_bytes()).hexdigest() in hashes
        with zipfile.ZipFile(wheel) as archive:
            assert archive.testzip() is None
            assert any(n.endswith(".dist-info/METADATA") for n in archive.namelist())
            assert any("license" in n.lower() or "copying" in n.lower() for n in archive.namelist())


def test_transcript_does_not_pass_preflight_even_with_pdf_header(tmp_path):
    result = check_environment(ROOT / "tests/fixtures/synthetic_transcript.pdf", tmp_path, "chrome")
    assert result["checks"]["psr_pdf_readable"]
    assert not result["checks"]["psr_content_supported"]
    assert result["psr_error"] == "psr_title_missing"


def test_supported_psr_still_cannot_claim_host_permissions(tmp_path):
    result = check_environment(ROOT / "tests/fixtures/synthetic_psr.pdf", tmp_path, "edge")
    assert result["checks"]["psr_content_supported"]
    assert result["checks"]["pdf_dependencies_available"]
    assert not result["ready_to_fill"]
    assert result["host_checks_required"]
