"""Install-test only the release files, never the private development workspace."""
from pathlib import Path
import argparse
import stat
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.validate_plugin import validate_archive

ROOT = Path(__file__).resolve().parents[1]


def stage(archive_path: Path) -> Path:
    validate_archive(archive_path)
    directory = ROOT / "work/local-plugin"
    directory.mkdir(parents=True, exist_ok=True)
    intended = directory.resolve()
    if directory.is_symlink() or not intended.is_relative_to((ROOT / "work").resolve()):
        raise ValueError("Unsafe staging target")
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        # Remove only stale regular stage files. Never follow a link or recursively
        # delete an unchecked Windows path. Private input paths are never involved.
        for file in directory.rglob("*"):
            if file.is_symlink():
                raise ValueError("Unexpected staging link")
            if file.is_file() and file.relative_to(directory).as_posix() not in names:
                if not file.resolve().is_relative_to(intended):
                    raise ValueError("Stale path escaped stage")
                file.unlink()
        for name in archive.namelist():
            if archive.getinfo(name).is_dir():
                continue
            target = directory / name
            if not target.resolve().is_relative_to(intended):
                raise ValueError("Entry escaped stage")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
    return directory


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    print(stage(parser.parse_args().archive))
