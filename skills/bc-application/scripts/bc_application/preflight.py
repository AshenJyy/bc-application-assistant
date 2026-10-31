"""Check only capabilities we can actually observe in a Python process."""
from __future__ import annotations

import platform
import sys
import tempfile
from pathlib import Path


def check_environment(psr: Path | None, profile_dir: Path, browser: str) -> dict:
    checks = {
        "windows": platform.system() == "Windows",
        "windows_x64": platform.machine().lower() in {"amd64", "x86_64"},
        "python_312": sys.version_info[:2] == (3, 12),
        "supported_browser": browser in {"chrome", "edge"},
        "psr_pdf_readable": False,
        "psr_content_supported": False,
        "pdf_dependencies_available": False,
        "profile_directory_writable": False,
    }
    if psr is not None and psr.suffix.lower() == ".pdf":
        try:
            with psr.open("rb") as stream:
                checks["psr_pdf_readable"] = stream.read(5) == b"%PDF-"
        except OSError:
            pass
    try:
        import pdfplumber
        checks["pdf_dependencies_available"] = True
    except ImportError:
        pass
    psr_error = None
    if checks["psr_pdf_readable"] and checks["pdf_dependencies_available"]:
        from .psr import PSRError, parse_psr
        try:
            parse_psr(psr)
            checks["psr_content_supported"] = True
        except PSRError as exc:
            psr_error = str(exc)
    if profile_dir.is_dir():
        try:
            with tempfile.NamedTemporaryFile(prefix=".bc-permission-", dir=profile_dir):
                checks["profile_directory_writable"] = True
        except OSError:
            pass
    return {
        "checks": checks,
        "local_checks_passed": all(checks.values()),
        "ready_to_fill": False,
        "host_checks_required": ["browser_connected", "target_origin_permitted", "login_state_observed"],
        "blockers": [key for key, passed in checks.items() if not passed],
        "psr_error": psr_error,
        "limitations": ["Local checks do not establish browser connection, login or current-page readiness",
                         "Only supported observed page configurations can be filled; unclear records require review"],
    }
