"""Prepare an isolated Python 3.12 runtime using only bundled, hashed wheels."""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import venv
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != "Windows" or sys.version_info[:2] != (3,12) or platform.machine().lower() not in {"amd64", "x86_64"}:
        parser.error("Beta requires Windows x64 with Python 3.12")
    directory = args.runtime_dir.resolve()
    if directory.exists() and any(directory.iterdir()) and not (directory / "pyvenv.cfg").is_file():
        parser.error("Runtime directory must be empty or an existing Python venv")
    venv.EnvBuilder(with_pip=True).create(directory)
    python = directory / "Scripts/python.exe"
    skill = Path(__file__).resolve().parents[1]
    subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--disable-pip-version-check",
                    "--find-links", str(skill / "assets/wheels"), "--require-hashes", "-r",
                    str(skill / "runtime-requirements.txt")], check=True)
    subprocess.run([str(python), "-c", "import pdfplumber; print(pdfplumber.__version__)"], check=True)
    print(json.dumps({"runtime_python": str(python), "offline_dependencies_ready": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
