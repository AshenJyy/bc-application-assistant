"""Conditional first-use rows, durable restart, and source-gated whole-page saves."""
import copy
import io
import json

import pytest

from bc_application import common_language as language
from bc_application.browser import digest,values
from bc_application.checkpoints import transaction_active
from bc_application.pages import build_plan,verify_saved,recovery_bundle
from bc_application.common_pages import resume as fixed_resume
from bc_application.profile import ProfileError,add_statement,set_fact
from bc_application.store import ProfileSnapshot,ProfileStore
from test_common_factual import setup,filled


def scenario(before=0,after=2):
    p,t,rows,ctx=setup(n=after)
    _,_,original,_=setup(n=before,complete=before>0)
    count=next(f for f in rows['fields'] if f['key']==language.COUNT)
    count['value']=next(o['value'] for o in count['options'] if o['label']==str(after))
    count['invalid']=False
    # One observed navigation set must stay consistent across a count change.
    rows['state_metadata']=copy.deepcopy(original['state_metadata'])
    return p,t,original,rows,ctx


@pytest.mark.parametrize('before,after',[(0,1),(0,5),(1,3),(3,1),(2,5),(5,2),(2,2)])
def test_count_then_fresh_rows_then_whole_saved_page(before,after):
    p,t,original,rows,ctx=scenario(before,after);raw=copy.deepcopy(p['academic'])
    unchanged=copy.deepcopy(p);report=language.preview(p,t,original)
    assert report['ready'] and p==unchanged and report['count_change_required']==(before!=after)
    first=language.prepare(p,t,original,ctx);key=first['checkpoint_id']
    cp=p['checkpoints'][key];journal=copy.deepcopy(cp['journal'])
    assert cp['journal']==values(original) and transaction_active(cp)
    assert all(w['field_key']==language.COUNT for w in first['plan']['writes'])
    assert not language.verify(p,key,rows,revisited_after_save=True)['verified']
    assert cp['journal']==journal
    second=language.prepare_rows(p,key,rows);plan=second['plan']
    assert second['stage']=='fields' and plan['ready'] and not any(w['field_key']==language.COUNT for w in plan['writes'])
    saved=filled(rows,plan)
    assert language.verify(p,key,saved,revisited_after_save=True)['verified']
    assert cp['journal'] is None and not transaction_active(cp) and p['academic']==raw
    assert 'language_transaction' not in cp and 'original_state_metadata' not in cp


@pytest.mark.parametrize('stage',['before_count','after_count','partial_fields','saved_mismatch'])
def test_one_json_restart_preserves_original_and_resumes_intended_update(stage,tmp_path):
    p,t,original,rows,ctx=scenario();first=language.prepare(p,t,original,ctx);key=first['checkpoint_id']
    store=ProfileStore(tmp_path/'applicant.json');snapshot=ProfileSnapshot(p,None);store.save(snapshot)
    page=original if stage=='before_count' else rows
    if stage in {'partial_fields','saved_mismatch'}:
        second=language.prepare_rows(snapshot.data,key,rows)
        page=filled(rows,second['plan']);page['fields'][1]['value']='English'
        if stage=='saved_mismatch':assert not language.verify(snapshot.data,key,page,revisited_after_save=True)['verified']
        store.save(snapshot)
    reloaded=store.load();journal=copy.deepcopy(reloaded.data['checkpoints'][key]['journal'])
    resumed=language.resume(reloaded.data,key,page)
    if stage=='before_count':
        assert resumed['stage']=='count'
        resumed=language.prepare_rows(reloaded.data,key,rows)
        page=rows
    assert resumed['stage']=='fields' and reloaded.data['checkpoints'][key]['journal']==journal==values(original)
    assert language.verify(reloaded.data,key,filled(page,resumed['plan']),revisited_after_save=True)['verified']
    store.save(reloaded)
    assert store.load().data['checkpoints'][key]['journal'] is None and len(list(tmp_path.glob('*.json')))==1


@pytest.mark.parametrize('case',['missing_flag','conflict','invalid_boolean','other_language','missing_order','duplicate_label','missing_psr'])
def test_all_required_source_answers_precede_count_selection(case,tmp_path):
    p,t,original,_,ctx=scenario()
    if case=='missing_flag':del p['facts']['personal.languages.language_1.read']
    if case=='conflict':set_fact(p,'personal.languages.language_1.read',True,add_statement(p,'Conflicting fictional answer.'))
    if case=='invalid_boolean':p['facts']['personal.languages.language_1.read']['value']='Yes'
    if case=='other_language':p['facts']['personal.languages.language_1.label']['value']='Other'
    if case=='missing_order':del p['facts']['personal.languages.order']
    if case=='duplicate_label':p['facts']['personal.languages.language_1.label']['value']='French'
    if case=='missing_psr':p['sources'][p['psr_source_id']]['path']=str(tmp_path/'missing.pdf')
    before=copy.deepcopy(p);result=language.prepare(p,t,original,ctx)
    assert not result['ready'] and p==before


def test_changed_sources_or_another_journal_cannot_replace_the_original():
    p,t,original,rows,ctx=scenario();first=language.prepare(p,t,original,ctx);key=first['checkpoint_id']
    p['facts']['personal.languages.language_1.read']['value']=True;before=copy.deepcopy(p)
    with pytest.raises(ProfileError,match='source_gate'):language.resume(p,key,rows)
    assert p==before
    p['checkpoints']['other']={'target_id':t,'page_key':'other','state':'prepared','journal':{'x':'old'}}
    before=copy.deepcopy(p)
    with pytest.raises(ProfileError,match='pending_transaction'):language.resume(p,key,rows)
    assert p==before


@pytest.mark.parametrize('case',['count_rows','count_options','unexpected_field','unrelated_state','new_option','invalid','not_revisited'])
def test_count_or_saved_drift_never_clears_recovery(case):
    p,t,original,rows,ctx=scenario();key=language.prepare(p,t,original,ctx)['checkpoint_id']
    if case=='count_rows':rows['fields'][0]['value']='0'
    if case=='count_options':rows['fields'][0]['options'][0]['label']='A different meaning'
    if case=='unexpected_field':rows['fields'].append({**rows['fields'][1],'key':'i:unknown'})
    if case in {'count_rows','count_options','unexpected_field'}:
        before=copy.deepcopy(p)
        with pytest.raises(ProfileError):language.prepare_rows(p,key,rows)
        assert p==before
    else:
        plan=language.prepare_rows(p,key,rows)['plan'];saved=filled(rows,plan)
        if case=='unrelated_state':saved['state_metadata']['items'][-1]['status']='complete'
        if case=='new_option':saved['choice_observations'][saved['fields'][1]['key']].append({'label':'Another','value':'Another','disabled':False})
        if case=='invalid':saved['fields'][1]['invalid']=True
        try:result=language.verify(p,key,saved,revisited_after_save=case!='not_revisited')
        except ProfileError:result={'verified':False}
        assert not result['verified']
    assert p['checkpoints'][key]['journal']==values(original)


@pytest.mark.parametrize('before',[0,2])
def test_unsaved_cancellation_requires_all_original_values_invalid_flags_and_states(before):
    p,t,original,rows,ctx=scenario(before,3);key=language.prepare(p,t,original,ctx)['checkpoint_id']
    language.prepare_rows(p,key,rows)
    assert not language.cancel(p,key,rows,revisited_saved_draft=True)['restored']
    p['facts']['personal.languages.language_0.label']['value']='Changed source after interruption'
    assert language.cancel(p,key,original,revisited_saved_draft=True)['restored']
    assert p['checkpoints'][key]['journal'] is None


def test_generic_fixed_shape_operations_cannot_bypass_the_staged_journal():
    p,t,original,rows,ctx=scenario();key=language.prepare(p,t,original,ctx)['checkpoint_id']
    before=copy.deepcopy(p)
    for call in (lambda:build_plan(p,t,rows),lambda:verify_saved(p,key,rows,revisited_after_save=True),
                 lambda:recovery_bundle(p,key,original),lambda:fixed_resume(p,key,original)):
        with pytest.raises(ProfileError):call()
        assert p==before


@pytest.mark.parametrize('flag',['real_account_test','restore_after_test'])
def test_count_changes_do_not_claim_real_account_test_restoration(flag):
    p,t,original,_,ctx=scenario();ctx[flag]=True;before=copy.deepcopy(p)
    with pytest.raises(ProfileError,match='intended_update_only'):language.prepare(p,t,original,ctx)
    assert p==before


def test_cli_preview_blocked_prepare_and_persisted_stage_restart(monkeypatch,capsys,tmp_path):
    from bc_application.cli import main
    p,t,original,rows,ctx=scenario();path=tmp_path/'applicant.json';store=ProfileStore(path);store.save(ProfileSnapshot(p,None))
    def cli(operation,payload,identifier=None):
        monkeypatch.setattr('sys.stdin',io.StringIO(json.dumps(payload)))
        code=main(['common-language-'+operation,'--profile',str(path),
            '--target' if operation in {'preview','prepare'} else '--checkpoint',identifier or t])
        result=json.loads(capsys.readouterr().out);assert code==0,result
        return result
    before=path.read_bytes();assert cli('preview',{'page':original})['ready'];assert path.read_bytes()==before
    first=cli('prepare',{'page':original,'context':ctx});key=first['checkpoint_id']
    assert store.load().data['checkpoints'][key]['journal']==values(original)
    second=cli('resume',{'page':rows},key)
    assert cli('verify',{'page':filled(rows,second['plan']),'revisited_after_save':True},key)['verified']
    assert len(list(tmp_path.glob('*.json')))==1


def test_cli_blocked_prepare_preserves_canonical_bytes(monkeypatch,capsys,tmp_path):
    from bc_application.cli import main
    p,t,original,_,ctx=scenario();del p['facts']['personal.languages.language_0.speak']
    path=tmp_path/'applicant.json';ProfileStore(path).save(ProfileSnapshot(p,None));before=path.read_bytes()
    monkeypatch.setattr('sys.stdin',io.StringIO(json.dumps({'page':original,'context':ctx})))
    assert main(['common-language-prepare','--profile',str(path),'--target',t])==0
    assert not json.loads(capsys.readouterr().out)['ready'] and path.read_bytes()==before
