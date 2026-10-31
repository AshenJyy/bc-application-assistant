"""Staged Common App language row creation with one durable intended-update journal.

Count selection only builds controls. All source-backed fields must be prepared
again from that actual new shape before any draft save. Real-account destructive
QA is deliberately excluded; saved interruptions resume the intended factual draft.
"""
import copy

from .browser import digest, permission_gate, structure, validate_observation, values
from .checkpoints import create_checkpoint, page_requirements, transaction_active
from .common_factual import CONTRACTS, validate
from .common_pages import state_matches
from .pages import build_plan, encode
from .profile import ProfileError, _event, now

SPEC=next(s for s in CONTRACTS if s['kind']=='language')
COUNT=SPEC['count_field']['key']
ORIGIN='https://apply.commonapp.org'


def _page(page):
    validate_observation(page);validate(page)
    if page['common_factual']['kind']!='language' or page['url']!=ORIGIN+SPEC['path']:
        raise ProfileError('observed_common_language_page_required')
    count=next(f for f in page['fields'] if f['key']==COUNT)
    options=count['options']
    if ([o['label'] for o in options]!=[str(i) for i in range(1,6)] or
            len({o['value'] for o in options})!=5 or any(o['disabled'] for o in options)):
        raise ProfileError('observed_language_count_choices_required')
    rows=len(page['common_factual']['rows'])
    selected=next((o['label'] for o in options if o['value']==count['value']),None)
    if (selected is None and (count['value']!='' or rows)) or (selected is not None and int(selected)!=rows):
        raise ProfileError('language_count_row_transition_incomplete')
    return count


def _requirements(profile):
    from .common_factual import language_requirements
    return language_requirements(profile)


def preview(profile,target_id,page):
    count=_page(page)
    if profile['targets'].get(target_id,{}).get('system')!='common_app':
        raise ProfileError('student_selected_common_target_required')
    if any(transaction_active(cp) for cp in profile['checkpoints'].values()):
        raise ProfileError('pending_transaction_requires_recovery')
    refs,issues=_requirements(profile)
    gate=page_requirements(profile,fact_ids=refs)
    order=profile['facts'].get('personal.languages.order',{}).get('value')
    n=len(order) if isinstance(order,list) and not issues else None
    return {'schema':'common-language-preview/1','ready':gate['data_ready'] and not issues,
        'target_id':target_id,'page_url':page['url'],'required_fact_ids':refs,'source_gate':gate,
        'blockers':issues,'desired_count':n,'observed_count':len(page['common_factual']['rows']),
        'count_change_required':n is not None and encode(count,n)!=count['value'],
        'profile_changed':False,'website_actions_performed':False}


def _fingerprint(profile,refs):
    return digest({ref:profile['facts'][ref] for ref in refs})


def _count_plan(cp,page,n):
    count=_page(page);value=encode(count,n)
    return {'schema':'common-language-count-plan/1','system':'common_app','ready':True,
        'checkpoint_id':cp['checkpoint_id'],'page_url':page['url'],'desired_count':n,
        'observation_sha256':digest(page),'common_factual':copy.deepcopy(page['common_factual']),
        'writes':[] if count['value']==value else [{'field_key':COUNT,'value':value}],
        'choice_observations':copy.deepcopy(page['choice_observations'])}


def prepare(profile,target_id,page,context):
    report=preview(profile,target_id,page)
    if context.get('real_account_test') or context.get('restore_after_test'):
        raise ProfileError('language_count_intended_update_only')
    permission_gate(context,page,ORIGIN)
    if not report['ready']:return report
    refs=report['required_fact_ids']
    key=create_checkpoint(profile,target_id,page['url'],fact_ids=refs)
    cp=profile['checkpoints'][key]
    cp.pop('verification_kind',None)
    cp.update(state='prepared',journal=values(page),context=copy.deepcopy(context),
        observed_structure=structure(page),original_state_metadata=copy.deepcopy(page['state_metadata']),
        original_invalid_fields=[f['key'] for f in page['fields'] if f['invalid']],
        original_values_sha256=digest(values(page)),prepared_at=now(),
        source_gate=report['source_gate'],language_transaction={'schema':'common-language-transaction/1',
            'stage':'count','desired_count':report['desired_count'],'facts_sha256':_fingerprint(profile,refs)})
    cp['prepared_plan']=_count_plan(cp,page,report['desired_count'])
    _event(profile,'common_language_count_prepared',[key])
    return {'ready':True,'stage':'count','checkpoint_id':key,'plan':copy.deepcopy(cp['prepared_plan'])}


def _active(profile,key,page,*,sources=True):
    cp=profile['checkpoints'].get(key)
    if (not cp or cp.get('journal') is None or cp.get('language_transaction',{}).get('schema')!='common-language-transaction/1'
            or not transaction_active(cp)):
        raise ProfileError('prepared_language_transaction_required')
    if any(k!=key and transaction_active(c) for k,c in profile['checkpoints'].items()):
        raise ProfileError('pending_transaction_requires_recovery')
    _page(page);permission_gate(cp['context'],page,ORIGIN)
    if cp['context'].get('real_account_test') or cp['context'].get('restore_after_test'):
        raise ProfileError('language_count_intended_update_only')
    if not state_matches(cp['original_state_metadata'],page['state_metadata'],SPEC['current_key'],SPEC['parent_key'],resume=True):
        raise ProfileError('common_language_unrelated_state_changed')
    if sources:
        refs,issues=_requirements(profile);gate=page_requirements(profile,fact_ids=refs)
        if (issues or not gate['data_ready'] or refs!=cp['required_fact_ids'] or
                _fingerprint(profile,refs)!=cp['language_transaction']['facts_sha256']):
            raise ProfileError('common_language_resume_source_gate_failed')
    return cp


def prepare_rows(profile,key,page):
    cp=_active(profile,key,page);n=cp['language_transaction']['desired_count']
    if len(page['common_factual']['rows'])!=n:
        raise ProfileError('required_language_count_not_observed')
    working=copy.deepcopy(profile);working['checkpoints']={}
    plan=build_plan(working,cp['target_id'],page)
    if not plan['ready'] or any(w['field_key']==COUNT for w in plan['writes']):
        raise ProfileError('observed_language_rows_source_gate_failed')
    plan['checkpoint_id']=key
    cp.update(state='prepared',prepared_plan=copy.deepcopy(plan),expected_values_sha256=plan['expected_values_sha256'])
    cp['language_transaction']['stage']='fields'
    _event(profile,'common_language_generated_rows_prepared',[key])
    return {'ready':True,'stage':'fields','checkpoint_id':key,'plan':plan}


def resume(profile,key,page):
    cp=_active(profile,key,page)
    if len(page['common_factual']['rows'])==cp['language_transaction']['desired_count']:
        return prepare_rows(profile,key,page)
    cp['prepared_plan']=_count_plan(cp,page,cp['language_transaction']['desired_count'])
    cp.update(state='prepared');cp['language_transaction']['stage']='count'
    return {'ready':True,'stage':'count','checkpoint_id':key,'plan':copy.deepcopy(cp['prepared_plan'])}


def verify(profile,key,page,*,revisited_after_save):
    cp=_active(profile,key,page)
    plan=cp['prepared_plan']
    okay=(revisited_after_save is True and cp['language_transaction']['stage']=='fields'
        and plan.get('schema')!='common-language-count-plan/1'
        and digest(structure(page))==plan['structure_sha256']
        and digest(values(page))==plan['expected_values_sha256']
        and page['choice_observations']==plan['choice_observations']
        and not any(f['invalid'] for f in page['fields'])
        and state_matches(cp['original_state_metadata'],page['state_metadata'],SPEC['current_key'],SPEC['parent_key']))
    if not okay:
        cp['state']='needs_restore'
        return {'verified':False,'state':'needs_restore','reason':'saved_language_page_mismatch_resume_required'}
    cp.update(state='verified',journal=None,observed_structure=structure(page),
        saved_state_sha256=digest(page['state_metadata']),last_verified_at=now(),verification_kind='staged_language_update')
    _finish(cp)
    _event(profile,'common_language_saved_page_verified',[key])
    return {'verified':True,'state':'verified','fields':len(page['fields']),'language_rows':len(page['common_factual']['rows'])}


def cancel(profile,key,page,*,revisited_saved_draft):
    cp=_active(profile,key,page,sources=False)
    okay=(revisited_saved_draft is True and digest(structure(page))==digest(cp['observed_structure'])
        and values(page)==cp['journal'] and page['state_metadata']==cp['original_state_metadata']
        and [f['key'] for f in page['fields'] if f['invalid']]==cp['original_invalid_fields'])
    if not okay:
        cp['state']='needs_restore'
        return {'restored':False,'state':'needs_restore','reason':'original_saved_language_draft_not_observed'}
    cp.update(state='restored',journal=None,last_verified_at=now())
    _finish(cp)
    _event(profile,'common_language_unsaved_update_canceled',[key])
    return {'restored':True,'state':'restored','restore_save_performed':False}


def _finish(cp):
    for key in ('language_transaction','prepared_plan','original_state_metadata','original_invalid_fields',
                'original_values_sha256','prepared_at'):
        cp.pop(key,None)
