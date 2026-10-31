"""Shared Common App saved-state verification and durable intended-fill restart."""
import copy

from .profile import ProfileError


def keys(page):
    if 'common_ielts' in page:return 'tertiaryNavItem2_10','secondaryNavItem2'
    from .common_factual import contract
    spec=contract(page)
    return spec['current_key'],spec['parent_key']


def state_matches(original,current,child,parent,*,resume=False):
    if (original.get('coverage')!='common_app_visible_navigation' or current.get('coverage')!=original['coverage']
            or original.get('current_page_key')!=child or current.get('current_page_key')!=child):return False
    before={i['key']:i['status'] for i in original.get('items',[])};after={i['key']:i['status'] for i in current.get('items',[])}
    if set(before)!=set(after) or not {child,parent}<=set(before):return False
    if any(after[k]!=v for k,v in before.items() if k not in {child,parent}):return False
    if resume:return True
    children=[k for k in before if k.startswith('tertiaryNavItem'+parent.removeprefix('secondaryNavItem')+'_')]
    expected='complete' if all(after[k]=='complete' for k in children) else 'in progress'
    return after[child]=='complete' and after[parent]==expected


def resume(profile,checkpoint_id,page):
    from .browser import digest,structure,validate_observation
    from .pages import build_plan
    from .checkpoints import transaction_active
    cp=profile['checkpoints'].get(checkpoint_id)
    if cp and cp.get('language_transaction'):raise ProfileError('staged_language_resume_required')
    if not cp or cp.get('journal') is None or not any(tag in cp.get('observed_structure',{}) for tag in ('common_ielts','common_factual')):
        raise ProfileError('prepared_common_page_checkpoint_required')
    if any(key!=checkpoint_id and transaction_active(other) for key,other in profile['checkpoints'].items()):
        raise ProfileError('pending_transaction_requires_recovery')
    validate_observation(page);child,parent=keys(page)
    if cp.get('context',{}).get('real_account_test') or not state_matches(cp.get('original_state_metadata',{}),page.get('state_metadata',{}),child,parent,resume=True):
        raise ProfileError('common_page_resume_state_changed')
    if digest(structure(page))!=digest(cp['observed_structure']):raise ProfileError('common_page_resume_shape_changed')
    working=copy.deepcopy(profile);working['checkpoints']={}
    plan=build_plan(working,cp['target_id'],page)
    if not plan['ready'] or plan['expected_values_sha256']!=cp['expected_values_sha256']:
        raise ProfileError('common_page_resume_source_gate_failed')
    plan['checkpoint_id']=checkpoint_id
    cp.update(state='prepared',prepared_plan=copy.deepcopy(plan),observation_sha256=plan['observation_sha256'])
    return plan
