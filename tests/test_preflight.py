from pathlib import Path

from bc_application.cli import main
from bc_application.preflight import check_environment


def test_missing_psr_refuses_and_never_claims_browser_readiness(tmp_path):
    result = check_environment(None, tmp_path, "chrome")
    assert "psr_pdf_readable" in result["blockers"]
    assert not result["ready_to_fill"]
    assert "target_origin_permitted" in result["host_checks_required"]
    assert list(tmp_path.iterdir()) == []


def test_unreadable_and_non_pdf_inputs_refuse(tmp_path):
    source = tmp_path / "wrong.pdf"
    source.write_text("transcript", encoding="utf-8")
    assert not check_environment(source, tmp_path, "edge")["local_checks_passed"]
    assert not check_environment(tmp_path / "missing.pdf", tmp_path, "edge")["local_checks_passed"]


def test_missing_profile_directory_is_not_created(tmp_path):
    directory = tmp_path / "not-selected"
    result = check_environment(None, directory, "chrome")
    assert "profile_directory_writable" in result["blockers"]
    assert not directory.exists()


def test_cli_reports_blockers_without_personal_content(tmp_path, capsys):
    assert main(["preflight", "--profile-dir", str(tmp_path), "--browser", "chrome"]) == 2
    assert '"ready_to_fill": false' in capsys.readouterr().out
