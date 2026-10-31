"""Local Agent Plugins schema and published ZIP conformance checks.

This cannot replace OpenAI's portal review/security scans.
"""
from __future__ import annotations

import argparse
import json
import re
import stat
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "tests/schemas/plugin.schema.json"
MAX_COMPRESSED = 100_000_000  # official: 100 MB
MAX_MEMBER = 100 * 1024 * 1024
MAX_EXTRACTED = 512 * 1024 * 1024


class PackageError(ValueError):
    pass


def validate_archive(path: Path) -> dict:
    if path.stat().st_size > MAX_COMPRESSED:
        raise PackageError("archive_too_large")
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise PackageError("archive_format_not_zip") from exc
    with archive:
        entries = archive.infolist()
        if not entries or len(entries) > 5000:
            raise PackageError("archive_empty_or_too_many_entries")
        normalized: set[str] = set()
        files: set[str] = set()
        total = 0
        for entry in entries:
            # ZipInfo.filename normalizes backslashes on Windows and truncates at
            # NUL. Inspect the original central-directory spelling before trusting it.
            name = entry.orig_filename
            parts = name.rstrip("/").split("/")
            if (not name or name != name.strip() or "\\" in name or name.startswith("/")
                    or any(p in {"", ".", ".."} or ":" in p for p in parts)
                    or len(parts) > 20 or len(name) > 240
                    or any(ord(c) < 32 or ord(c) == 127 for c in name)):
                raise PackageError("archive_member_path_unsafe")
            key = unicodedata.normalize("NFC", name.rstrip("/")).casefold()
            if key in normalized:
                raise PackageError("archive_member_path_normalization_collision")
            normalized.add(key)
            file_type = stat.S_IFMT(entry.external_attr >> 16)
            if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                raise PackageError("archive_member_type_unsupported")
            if entry.flag_bits & 1 or entry.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                raise PackageError("archive_member_unreadable")
            if entry.file_size > MAX_MEMBER:
                raise PackageError("archive_member_too_large")
            total += entry.file_size
            if total > MAX_EXTRACTED:
                raise PackageError("archive_uncompressed_too_large")
            if not entry.is_dir():
                files.add(name)
        canonical_files = {unicodedata.normalize("NFC", f).casefold() for f in files}
        for name in canonical_files:
            if any(parent.as_posix() in canonical_files for parent in PurePosixPath(name).parents
                   if parent.as_posix() != "."):
                raise PackageError("archive_member_path_type_conflict")
        if archive.testzip() is not None:
            raise PackageError("archive_corrupt_member")
        roots = [f[:-len("plugin.json")] for f in files
                 if f == "plugin.json" or (f.count("/") == 1 and f.endswith("/plugin.json"))]
        if len(roots) != 1:
            raise PackageError("plugin_root_missing_or_ambiguous")
        prefix = roots[0]
        if prefix and any(not f.startswith(prefix) for f in files):
            raise PackageError("plugin_root_has_siblings")
        relative = {f[len(prefix):] for f in files}
        for name in relative:
            if (name in {"mcp.json", ".mcp.json", ".app.json"} or "hooks" in name.split("/")
                    or name.startswith(("work/", "outputs/", "private/", "applicant-data/", ".git/"))
                    or name.endswith((".pdf", ".log", ".env"))):
                raise PackageError("unexpected_beta_component_or_private_file")
        try:
            manifest = json.loads(archive.read(prefix + "plugin.json").decode("utf-8"))
            schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
            jsonschema.Draft202012Validator(schema).validate(manifest)
        except (UnicodeError, json.JSONDecodeError, jsonschema.ValidationError) as exc:
            raise PackageError("plugin_manifest_invalid") from exc
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", manifest["name"]):
            raise PackageError("plugin_name_not_submission_compatible")
        extension = manifest.get("extensions", {}).get("com.openai", {})
        if extension.get("requires_local_executor") is not True:
            raise PackageError("desktop_execution_flag_missing")
        if any(k in extension for k in ("apps", "hooks", "mcpServers")):
            raise PackageError("app_configuration_excluded")
        interface = extension.get("interface", {})
        if "screenshots" in interface:
            raise PackageError("screenshot_configuration_excluded")
        for key in ("composerIcon", "logo"):
            asset = interface.get(key)
            if not isinstance(asset, str) or not asset.startswith("./") or ".." in asset.split("/"):
                raise PackageError("branding_asset_path_unsafe")
            if asset[2:] not in relative:
                raise PackageError("declared_asset_file_missing")
        skills = [f for f in relative if re.fullmatch(r"skills/[^/.][^/]*/SKILL\.md", f)]
        if not skills:
            raise PackageError("plugin_runtime_surface_missing")
        identities: set[str] = set()
        for skill in skills:
            text = archive.read(prefix + skill).decode("utf-8")
            match = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n(.+)\Z", text, re.DOTALL)
            if not match:
                raise PackageError("skill_frontmatter_or_body_missing")
            try:
                front = yaml.safe_load(match[1])
            except yaml.YAMLError as exc:
                raise PackageError("skill_frontmatter_yaml_malformed") from exc
            if not isinstance(front, dict) or any(not isinstance(front.get(k), str) or not front[k].strip()
                                                  for k in ("name", "description")):
                raise PackageError("skill_metadata_invalid")
            if len(front["description"]) > 1024 or len(manifest["name"] + ":" + front["name"]) > 64:
                raise PackageError("skill_metadata_too_long")
            if front["name"] in identities:
                raise PackageError("skill_identity_duplicate")
            identities.add(front["name"])
            # Verify packaged Markdown references, including references outside the skill.
            for link in re.findall(r"\]\(([^)]+)\)", match[2]):
                if "://" not in link and not link.startswith("#"):
                    target = PurePosixPath(skill).parent / link.split("#")[0]
                    stack: list[str] = []
                    for part in target.parts:
                        if part == "..":
                            if not stack:
                                raise PackageError("skill_reference_outside_package")
                            stack.pop()
                        elif part != ".":
                            stack.append(part)
                    if "/".join(stack) not in relative:
                        raise PackageError("skill_reference_missing")
        onboarding = extension.get("onboardingSkill")
        if onboarding and (not onboarding.startswith("./") or onboarding[2:] not in skills):
            raise PackageError("onboarding_skill_missing")
        return {"valid": True, "name": manifest["name"], "version": manifest.get("version"),
                "files": len(files), "skills": sorted(identities), "compressed_bytes": path.stat().st_size,
                "uncompressed_bytes": total, "public_directory_review": "not_run"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(validate_archive(args.archive), indent=2))
    except (PackageError, OSError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
