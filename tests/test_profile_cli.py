import json
import io
import os
import subprocess
import sys
from pathlib import Path

from bc_application.cli import main
from bc_application.store import ProfileStore

FIXTURE = Path(__file__).parent/"fixtures/synthetic_psr.pdf"


def test_profile_cli_atomic_batch_and_private_summary(tmp_path,capsys):
    profile = tmp_path/"applicant.json"
    assert main(["profile-init","--psr",str(FIXTURE),"--profile",str(profile)]) == 0
    operations = tmp_path/"operations.json"
    operations.write_text(json.dumps([
        {"op":"statement","id":"name-source","text":"Synthetic student explicitly says their name is Example."},
        {"op":"fact","field":"personal.legal_given_name","value":"Example","source":"name-source"}
    ]))
    assert main(["profile-update","--profile",str(profile),"--operations",str(operations)]) == 0
    assert ProfileStore(profile).load().data["facts"]["personal.legal_given_name"]["value"] == "Example"
    assert "Example" not in capsys.readouterr().out
    before = profile.read_bytes()
    operations.write_text(json.dumps([
        {"op":"statement","id":"s","text":"Synthetic data"},
        {"op":"fact","field":"contact.city","value":"Cedar","source":"s"},
        {"op":"submit_application"}
    ]))
    assert main(["profile-update","--profile",str(profile),"--operations",str(operations)]) == 2
    assert profile.read_bytes() == before
    assert main(["profile-init","--psr",str(FIXTURE),"--profile",str(profile)]) == 2
    assert profile.read_bytes() == before


def test_confirmed_marker_clarification_is_not_repeated_after_restart(tmp_path):
    profile = tmp_path/"applicant.json"
    assert main(["profile-init","--psr",str(FIXTURE),"--profile",str(profile)]) == 0
    data = ProfileStore(profile).load().data
    record = next(r for r in data["academic"]["courses"] if r["raw_cells"]["equivalency_marker"])
    operations = tmp_path/"operations.json"
    operations.write_text(json.dumps([
        {"op":"statement","id":"s","text":"For this synthetic course only E denotes transfer credit.","scope":[record["record_id"]]},
        {"op":"marker_explanation","records":[record["record_id"]],"meaning":"equivalency_credit","source":"s"}
    ]))
    assert main(["profile-update","--profile",str(profile),"--operations",str(operations)]) == 0
    from bc_application.profile import review_requirements
    loaded = ProfileStore(profile).load().data
    requirement = review_requirements(loaded,record["record_id"])[0]
    assert not requirement["student_clarification_required"]
    assert requirement["transcript_or_report_card_review_required"]


def test_stdin_factual_updates_need_no_second_personal_data_file(tmp_path,monkeypatch,capsys):
    profile=tmp_path/'applicant.json'
    assert main(['profile-init','--psr',str(FIXTURE),'--profile',str(profile)])==0
    operations=[{'op':'statement','id':'s','text':'Invented student confirms no former-name materials.'},
        {'op':'fact','field':'personal.has_materials_under_former_legal_name','value':False,'source':'s'}]
    monkeypatch.setattr('sys.stdin',io.StringIO(json.dumps(operations)))
    assert main(['profile-update','--profile',str(profile),'--stdin'])==0
    assert [p.name for p in tmp_path.iterdir()]==['applicant.json']
    before=profile.read_bytes()
    monkeypatch.setattr('sys.stdin',io.StringIO(json.dumps([
        {'op':'statement','id':'s','text':'Synthetic forbidden update'},
        {'op':'fact','field':'personal.password','value':'Forbidden synthetic value','source':'s'}])))
    assert main(['profile-update','--profile',str(profile),'--stdin'])==2
    assert profile.read_bytes()==before
    assert 'Forbidden synthetic value' not in capsys.readouterr().out


def test_utf8_host_stdin_overrides_windows_legacy_pipe_encoding(tmp_path):
    profile=tmp_path/'applicant.json'
    assert main(['profile-init','--psr',str(FIXTURE),'--profile',str(profile)])==0
    text='Invented student says: Québec — 中文 “confirmed”.'
    operations=[{'op':'statement','id':'s','text':text},
        {'op':'fact','field':'contact.city','value':'Québec 中文','source':'s'}]
    env={**os.environ,'PYTHONIOENCODING':'cp1252:surrogateescape'}
    runner=Path(__file__).resolve().parents[1]/'skills/bc-application/scripts/run.py'
    result=subprocess.run([sys.executable,'-B',str(runner),'profile-update',
        '--profile',str(profile),'--stdin'],input=json.dumps(operations,ensure_ascii=False).encode('utf-8'),
        capture_output=True,env=env,check=False)
    assert result.returncode==0,result.stdout
    assert json.loads(result.stdout.decode('utf-8'))['ok']
    data=ProfileStore(profile).load().data
    assert data['facts']['contact.city']['value']=='Québec 中文'
    assert any(s.get('text')==text for s in data['sources'].values())
    assert [p.name for p in tmp_path.iterdir()]==['applicant.json']
