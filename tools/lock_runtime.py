"""Record hashes and versions of the Windows/Python 3.12 offline wheelhouse."""
import hashlib
import json
import zipfile
from email.parser import BytesParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/bc-application"


def lock():
    lines = ["# Windows x64, Python 3.12; all dependencies bundled; do not fetch at runtime."]
    files = []
    for wheel in sorted((SKILL / "assets/wheels").glob("*.whl")):
        with zipfile.ZipFile(wheel) as archive:
            metadata_files = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
            if len(metadata_files) != 1:
                raise ValueError("Ambiguous wheel metadata")
            meta = BytesParser().parsebytes(archive.read(metadata_files[0]))
        lines.append(f"{meta['Name']}=={meta['Version']} --hash=sha256:{hashlib.sha256(wheel.read_bytes()).hexdigest()}")
        files.append(wheel.relative_to(ROOT).as_posix())
    if not files:
        raise ValueError("Wheelhouse is empty")
    (SKILL / "runtime-requirements.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest_path = ROOT / "tools/release_files.json"
    paths = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = [p for p in paths if not p.startswith("skills/bc-application/assets/wheels/")]
    manifest_path.write_text(json.dumps(sorted(set(paths + files)), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    lock()
