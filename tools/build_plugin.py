"""Reproducible allowlisted ZIP build, independent of Git/untracked private data."""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.validate_plugin import PackageError, validate_archive

ROOT = Path(__file__).resolve().parents[1]


def build(root: Path = ROOT, output_dir: Path | None = None) -> Path:
    output_dir = output_dir or root / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((root / "plugin.json").read_text(encoding="utf-8"))
    paths = json.loads((root / "tools/release_files.json").read_text(encoding="utf-8"))
    if not isinstance(paths, list) or not paths or len(paths) != len(set(paths)):
        raise PackageError("invalid_release_allowlist")
    target = output_dir / f"{manifest['name']}-{manifest['version']}.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in sorted(paths):
            if not isinstance(relative, str) or "\\" in relative or ":" in relative:
                raise PackageError("release_path_unsafe")
            file = root / relative
            if file.is_symlink() or not file.is_file() or not file.resolve().is_relative_to(root.resolve()):
                raise PackageError("release_file_missing_or_unsafe")
            if any(parent.is_symlink() for parent in file.parents if parent != root.parent):
                raise PackageError("release_parent_symlink")
            info = zipfile.ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, file.read_bytes())
    report = validate_archive(target)
    report["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    print(build(output_dir=args.output_dir))
