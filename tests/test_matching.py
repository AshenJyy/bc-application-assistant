"""Source-ready local matches still require an independent saved read."""
import copy
import io
import json

import pytest

from bc_application.pages import build_plan,prepare,verify_matching,verify_saved
from bc_application.profile import ProfileError
from test_common_factual import setup,filled


def matching(kind='language'):
    p,t,page,ctx=setup(kind);page=filled(page,build_plan(p,t,page))
    p['checkpoints']={}
    return p,t,page,ctx


@pytest.mark.parametrize('kind',['household','language'])
def test_independent_saved_read_records_verification_without_input_or_journal(kind):
    p,t,page,ctx=matching(kind);saved=copy.deepcopy(page)
    for f in saved['fields']:
        if f['control']=='radio':f['name']='mat-radio-group-99'
    result=verify_matching(p,t,page,saved,ctx,revisited_saved_draft=True)
    assert result['verified'] and result['website_actions_performed'] is False
    cp=p['checkpoints'][result['checkpoint_id']]
    assert cp['journal'] is None and cp['verification_kind']=='read_only_saved_match'
    assert 'prepared_plan' not in cp
    with pytest.raises(ProfileError,match='dedicated_verification'):
        verify_saved(p,result['checkpoint_id'],saved,revisited_after_save=True)
    # A later authorized change still uses the ordinary preparation workflow.
    plan=build_plan(p,t,saved)
    assert 'verification_kind' not in p['checkpoints'][plan['checkpoint_id']]


@pytest.mark.parametrize('case',['not_revisited','saved_old_value','incomplete','unrelated_status','options','invalid','missing_source','different_canonical_answer'])
def test_unsaved_or_unsupported_matches_do_not_change_profile_or_create_recovery(case):
    p,t,page,ctx=matching();saved=copy.deepcopy(page)
    if case=='saved_old_value':saved['fields'][1]['value']='English'
    if case=='incomplete':saved['state_metadata']['items'][1]['status']='in progress'
    if case=='unrelated_status':saved['state_metadata']['items'][-1]['status']='complete'
    if case=='options':saved['choice_observations'][saved['fields'][1]['key']].reverse()
    if case=='invalid':saved['fields'][1]['invalid']=True
    if case=='missing_source':del p['facts']['personal.languages.language_0.speak']
    if case=='different_canonical_answer':p['facts']['personal.languages.language_0.label']['value']='English'
    before=copy.deepcopy(p)
    result=verify_matching(p,t,page,saved,ctx,revisited_saved_draft=case!='not_revisited')
    assert not result['verified'] and p==before and not p['checkpoints']


def test_active_journal_and_missing_browser_permission_stop_read_only_verification():
    p,t,page,ctx=matching();before=copy.deepcopy(p)
    with pytest.raises(ProfileError,match='permission'):
        verify_matching(p,t,page,page,{**ctx,'access_verified':False},revisited_saved_draft=True)
    assert p==before
    plan=build_plan(p,t,page);prepare(p,plan['checkpoint_id'],page,ctx);before=copy.deepcopy(p)
    with pytest.raises(ProfileError,match='pending_transaction'):
        verify_matching(p,t,page,page,ctx,revisited_saved_draft=True)
    assert p==before


@pytest.mark.parametrize('succeed',[True,False])
def test_cli_only_persists_successful_matching_verification(tmp_path,monkeypatch,capsys,succeed):
    from bc_application.cli import main
    from bc_application.store import ProfileStore,ProfileSnapshot
    p,t,page,ctx=matching();saved=copy.deepcopy(page)
    if not succeed:saved['fields'][1]['value']='English'
    path=tmp_path/'applicant.json';store=ProfileStore(path);store.save(ProfileSnapshot(p,None));before=path.read_bytes()
    monkeypatch.setattr('sys.stdin',io.StringIO(json.dumps({'baseline':page,'page':saved,'context':ctx,'revisited_saved_draft':True})))
    assert main(['page-verify-matching','--profile',str(path),'--target',t])==0
    assert json.loads(capsys.readouterr().out)['verified'] is succeed
    assert (path.read_bytes()!=before) is succeed
    assert len(list(tmp_path.glob('*.json')))==1
    assert all(cp.get('journal') is None for cp in store.load().data['checkpoints'].values())
