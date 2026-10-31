"""One authoritative JSON, atomic replacement and stale-writer protection."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .checkpoints import transaction_active
from .profile import ProfileError, from_extraction, now, validate_profile


class StoreError(ProfileError):
    pass


@dataclass
class ProfileSnapshot:
    data: dict
    base_sha256: str | None


@contextmanager
def _mutex(path: Path):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE,wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        name = "Local\\bc-applicant-" + hashlib.sha256(str(path.resolve()).casefold().encode()).hexdigest()
        handle = kernel.CreateMutexW(None, False, name)
        if not handle:
            raise StoreError("profile_lock_unavailable")
        acquired = False
        try:
            result = kernel.WaitForSingleObject(handle, 0)
            if result not in {0, 0x80}:  # acquired, or abandoned previous writer
                raise StoreError("profile_busy")
            acquired = True
            yield
        finally:
            if acquired:
                kernel.ReleaseMutex(handle)
            kernel.CloseHandle(handle)
    else:
        # Core remains reusable in a future non-Windows executor. This lock stores
        # no applicant values; Windows uses a named mutex and needs no sidecar.
        import fcntl
        with path.with_suffix(".lock").open("a+b") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise StoreError("profile_busy") from exc
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def migrate(data: dict) -> dict:
    if not isinstance(data,dict):
        raise StoreError("unsupported_profile_schema")
    if data.get("schema_version") == "psr-extraction/1":
        return from_extraction(data)
    validate_profile(data)
    return data


class ProfileStore:
    def __init__(self, path: Path):
        self.path = path.resolve()
        if self.path.suffix.lower() != ".json" or not self.path.parent.is_dir():
            raise StoreError("existing_private_directory_and_json_filename_required")
        skill = Path(__file__).resolve().parents[2]
        if self.path.is_relative_to(skill):
            raise StoreError("profile_cannot_be_saved_in_skill_resources")

    def load(self) -> ProfileSnapshot:
        try:
            data = self.path.read_bytes()
            parsed = json.loads(data.decode("utf-8"))
        except (OSError,UnicodeError,json.JSONDecodeError) as exc:
            raise StoreError("profile_unreadable_or_invalid_json") from exc
        return ProfileSnapshot(migrate(parsed), hashlib.sha256(data).hexdigest())

    def save(self, snapshot: ProfileSnapshot, *, explicit_new_fact_ids=()) -> None:
        validate_profile(snapshot.data)
        with _mutex(self.path):
            current = self.path.read_bytes() if self.path.exists() else None
            current_hash = hashlib.sha256(current).hexdigest() if current is not None else None
            if current_hash != snapshot.base_sha256:
                raise StoreError("profile_changed_reload_before_save")
            if current is not None:
                previous = json.loads(current)
                if previous.get("schema_version") == "applicant-profile/1":
                    if (previous["profile_id"] != snapshot.data["profile_id"]
                            or previous["revision"] != snapshot.data["revision"]):
                        raise StoreError("profile_identity_or_revision_changed")
                    if previous["academic"] != snapshot.data["academic"] or previous["psr_source_id"] != snapshot.data["psr_source_id"]:
                        raise StoreError("raw_psr_data_cannot_be_overwritten")
                    active = any(transaction_active(cp) for cp in previous["checkpoints"].values())
                    if active and any(previous.get(key) != snapshot.data.get(key) for key in
                        ("sources","facts","exams","marker_explanations","reviews","conflicts","targets","school_directory")):
                        from .generic_forms import pending_fact_append_allowed
                        if not pending_fact_append_allowed(previous,snapshot.data,explicit_new_fact_ids=explicit_new_fact_ids):
                            raise StoreError("browser_transaction_active_recover_before_fact_edit")
            saved = copy.deepcopy(snapshot.data)
            saved["revision"] += 1
            saved["updated_at"] = now()
            encoded = (json.dumps(saved, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(prefix=f".{self.path.stem}-", suffix=".tmp", dir=self.path.parent,
                                                  delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
            finally:
                if temporary is not None and temporary.exists():
                    if not temporary.resolve().is_relative_to(self.path.parent):
                        raise StoreError("temporary_path_outside_profile_directory")
                    temporary.unlink()
            snapshot.data = saved
            snapshot.base_sha256 = hashlib.sha256(encoded).hexdigest()
