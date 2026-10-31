import json
import multiprocessing
import time
from pathlib import Path

import pytest

from bc_application.profile import ProfileError, add_statement, create_profile, set_fact
from bc_application.psr import parse_psr
from bc_application.store import ProfileSnapshot, ProfileStore, StoreError, _mutex

FIXTURE = Path(__file__).parent / "fixtures/synthetic_psr.pdf"


def fresh_store(tmp_path):
    store = ProfileStore(tmp_path/"applicant.json")
    snapshot = ProfileSnapshot(create_profile(FIXTURE),None)
    store.save(snapshot)
    return store,snapshot


def test_atomic_single_json_roundtrip_and_revision(tmp_path):
    store,snapshot = fresh_store(tmp_path)
    assert snapshot.data["revision"] == 1
    loaded = store.load()
    assert loaded.data == snapshot.data
    source = add_statement(loaded.data,"Synthetic confirmed first name.")
    set_fact(loaded.data,"personal.legal_given_name","Synthetic",source)
    store.save(loaded)
    assert store.load().data["revision"] == 2
    assert [p.name for p in tmp_path.iterdir()] == ["applicant.json"]


def test_stale_writer_and_manual_file_edits_are_rejected(tmp_path):
    store,_ = fresh_store(tmp_path)
    a,b = store.load(),store.load()
    store.save(a)
    with pytest.raises(StoreError,match="changed_reload"):
        store.save(b)
    c = store.load()
    text = store.path.read_text()
    store.path.write_text(text.replace('"2027-fall"','"2028-fall"'))
    with pytest.raises(StoreError,match="changed_reload"):
        store.save(c)


def test_failed_replace_preserves_original_and_cleans_temporary(tmp_path,monkeypatch):
    store,_ = fresh_store(tmp_path)
    before = store.path.read_bytes()
    loaded = store.load()
    import bc_application.store as module
    def fail(*args):
        raise OSError("simulated_replace_failure")
    monkeypatch.setattr(module.os,"replace",fail)
    with pytest.raises(OSError,match="simulated"):
        store.save(loaded)
    assert store.path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [store.path]


def hold_lock(path,ready,release):
    with _mutex(Path(path)):
        ready.set()
        release.wait(10)


def test_cross_process_lock_is_real_and_releases_when_writer_exits(tmp_path):
    store,_ = fresh_store(tmp_path)
    context = multiprocessing.get_context("spawn")
    ready,release = context.Event(),context.Event()
    child = context.Process(target=hold_lock,args=(str(store.path),ready,release))
    child.start()
    try:
        assert ready.wait(10)
        with pytest.raises(StoreError,match="profile_busy"):
            store.save(store.load())
    finally:
        release.set()
        child.join(10)
        if child.is_alive():
            child.terminate()
            child.join()
    store.save(store.load())
    assert store.load().data["revision"] == 2


def test_extraction_migration_uses_same_file_and_rejects_future_schema(tmp_path):
    path = tmp_path/"applicant.json"
    path.write_text(json.dumps(parse_psr(FIXTURE)),encoding="utf-8")
    store = ProfileStore(path)
    migrated = store.load()
    assert migrated.data["schema_version"] == "applicant-profile/1"
    store.save(migrated)
    assert len(list(tmp_path.glob("*.json"))) == 1
    data = store.load().data
    data["schema_version"] = "applicant-profile/99"
    path.write_text(json.dumps(data))
    with pytest.raises(ProfileError,match="unsupported_profile"):
        store.load()
