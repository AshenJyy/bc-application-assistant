import json
import stat
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

from tools.build_plugin import ROOT, build
from tools.validate_plugin import PackageError, validate_archive


def test_manifest_python_metadata_and_runtime_versions_agree():
    from bc_application import __version__
    manifest=json.loads((ROOT/'plugin.json').read_text(encoding='utf-8'))
    metadata=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))
    assert manifest['version'].replace('-dev.','.dev')==metadata['project']['version']==__version__


@pytest.fixture(scope="module")
def package(tmp_path_factory):
    return build(output_dir=tmp_path_factory.mktemp("plugin-package"))


def rewrite(package, tmp_path, transform):
    with zipfile.ZipFile(package) as archive:
        entries = [(i, archive.read(i)) for i in archive.infolist()]
    target = tmp_path / "mutated.zip"
    with zipfile.ZipFile(target, "w") as archive:
        for info, content in transform(entries):
            archive.writestr(info, content)
    return target


def test_official_schema_and_reproducible_allowlisted_build(package, tmp_path):
    assert validate_archive(package)["valid"]
    before = package.read_bytes()
    assert build(output_dir=tmp_path).read_bytes() == before
    with zipfile.ZipFile(package) as archive:
        assert set(archive.namelist()) == set(json.loads((ROOT / "tools/release_files.json").read_text()))
        assert not any("work/" in n or n.endswith(".pdf") for n in archive.namelist())


def test_extracted_plugin_runs_outside_checkout(package, tmp_path):
    isolated = tmp_path / "isolated"
    with zipfile.ZipFile(package) as archive:
        archive.extractall(isolated)
    runner = isolated / "skills/bc-application/scripts/run.py"
    version = subprocess.run([sys.executable, str(runner), "--version"], cwd=tmp_path, capture_output=True, text=True)
    assert version.returncode == 0, version.stderr
    assert version.stdout.strip().startswith("0.1.0")
    missing = subprocess.run([sys.executable, str(runner), "preflight", "--profile-dir", str(tmp_path),
                              "--browser", "chrome"], cwd=tmp_path, capture_output=True, text=True)
    assert missing.returncode == 2
    assert "psr_pdf_readable" in json.loads(missing.stdout)["blockers"]


@pytest.mark.parametrize("name", ["../escape.txt", "/absolute.txt", "C:/absolute.txt", "a\\b.txt",
                                   "a//b.txt", " ./file.txt", "a/./b.txt", "a/../b.txt", "a:b.txt"])
def test_rejects_unsafe_zip_paths(package, tmp_path, name):
    info = zipfile.ZipInfo(name)
    # Windows ZipInfo normalizes backslashes at construction; preserve the malicious
    # central-directory spelling so this really tests an unsafe archive.
    info.filename = name
    target = rewrite(package, tmp_path, lambda entries: entries + [(info, b"x")])
    with pytest.raises(PackageError, match="path_unsafe"):
        validate_archive(target)


@pytest.mark.parametrize("name", ["PLUGIN.JSON", "work/private.txt", "student.pdf", ".app.json", "mcp.json", "hooks/run.py"])
def test_rejects_collisions_private_data_and_forbidden_components(package, tmp_path, name):
    target = rewrite(package, tmp_path, lambda entries: entries + [(zipfile.ZipInfo(name), b"x")])
    with pytest.raises(PackageError):
        validate_archive(target)


def test_rejects_symlink(package, tmp_path):
    info = zipfile.ZipInfo("link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    target = rewrite(package, tmp_path, lambda entries: entries + [(info, b"outside")])
    with pytest.raises(PackageError, match="type_unsupported"):
        validate_archive(target)


def test_manifest_schema_error_is_not_silently_accepted(package, tmp_path):
    def change(entries):
        return [(info, b'{"name":"x","$schema":"wrong"}' if info.filename == "plugin.json" else data)
                for info, data in entries]
    with pytest.raises(PackageError, match="manifest_invalid"):
        validate_archive(rewrite(package, tmp_path, change))


def test_missing_runtime_reference_is_rejected(package, tmp_path):
    target = rewrite(package, tmp_path, lambda entries: [(i,d) for i,d in entries if i.filename != "PRIVACY.md"])
    with pytest.raises(PackageError, match="reference_missing"):
        validate_archive(target)


def test_top_level_directory_is_valid_but_sibling_is_not(package, tmp_path):
    def prefix(entries):
        result = []
        for info, data in entries:
            info.filename = "plugin/" + info.filename
            result.append((info, data))
        return result
    nested = rewrite(package, tmp_path, prefix)
    assert validate_archive(nested)["valid"]
    with zipfile.ZipFile(nested, "a") as archive:
        archive.writestr("sibling.txt", "x")
    with pytest.raises(PackageError, match="siblings"):
        validate_archive(nested)
