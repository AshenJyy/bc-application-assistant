"""Read-only factual requirement inventory from observed application pages.

This records evidence of coverage, never promotes current website answers into
canonical facts and never treats an uninspected record editor as completed.
"""
import copy
from urllib.parse import urlsplit

from .adapters import get_adapter
from .browser import digest, validate_observation
from .checkpoints import transaction_active
from .pages import build_plan
from .profile import ProfileError


def inventory(profile,target_id,pages,routes):
    target=profile['targets'].get(target_id)
    if not target:raise ProfileError('student_selected_target_required')
    adapter=get_adapter(target['system'])
    if any(transaction_active(cp) for cp in profile['checkpoints'].values()):
        raise ProfileError('pending_transaction_requires_recovery')
    if not isinstance(pages,list) or not isinstance(routes,list) or not routes or len(pages)>250 or len(routes)>250:
        raise ProfileError('bounded_observed_page_inventory_required')
    observed={}
    for route in routes:
        if (not isinstance(route,dict) or set(route)!={'url','label'} or not isinstance(route['label'],str)
                or not route['label'].strip() or not isinstance(route['url'],str)):
            raise ProfileError('actual_navigation_route_required')
        parsed=urlsplit(route['url'])
        if parsed.scheme+'://'+parsed.netloc!=adapter.application_origin or parsed.fragment:
            raise ProfileError('observed_inventory_origin_mismatch')
        if route['url'] in observed:raise ProfileError('unique_observed_inventory_routes_required')
        observed[route['url']]=route['label']
    results=[];seen=set()
    for page in pages:
        if not isinstance(page,dict) or page.get('url') not in observed or page['url'] in seen:
            raise ProfileError('unique_observed_inventory_page_required')
        seen.add(page['url'])
        try:validate_observation(page)
        except ProfileError as exc:
            # A rejected observation cannot authorize a fill or hide the gaps on
            # other routes. Keep only diagnostics, never raw applicant answers.
            results.append({'page_url':page['url'],'label':observed[page['url']],
                'observation_sha256':digest(page),'observation_valid':False,'ready_to_prepare':False,
                'fields':[],'record_collections':[],'missing_fact_ids':[],'conflicted_fact_ids':[],
                'required_fact_ids':[],'planned_write_count':None,'already_matches':False,
                'academic_reviews':[],'source_issues':[],'manual_fields':[],
                'blockers':[{'reason':'observation_requires_review','details':str(exc)}],'recommendations':[]})
            continue
        working=copy.deepcopy(profile)
        plan=build_plan(working,target_id,page)
        fields=[]
        for f in page['fields']:
            required=adapter.required_for_page(f,page)
            manual=adapter.manual(f)
            ref=None if manual else adapter.binding_for_page(f,target,profile,page)
            related=[b['reason'] for b in plan['blockers'] if b.get('field_key')==f['key']]
            fields.append({'field_key':f['key'],'label':f['label'],'required':required,'control':f['control'],
                'status':'manual' if manual else 'blocked' if related else 'mapped' if ref else 'unmapped',
                'fact_ref':ref,'blockers':related})
        cp=working['checkpoints'][plan['checkpoint_id']]
        gate=cp['source_gate']
        results.append({'page_url':page['url'],'label':observed[page['url']],'observation_sha256':digest(page),
            'observation_valid':True,'ready_to_prepare':plan['ready'],'fields':fields,'record_collections':copy.deepcopy(page.get('collections',[])),
            'missing_fact_ids':gate['missing_fact_ids'],'conflicted_fact_ids':gate['conflicted_fact_ids'],
            'academic_reviews':gate['academic_reviews'],'source_issues':gate['source_issues'],
            'manual_fields':cp['manual_fields_remaining'],'blockers':plan['blockers'],
            'required_fact_ids':list(dict.fromkeys(cp['required_fact_ids'])),
            'planned_write_count':len(plan['writes']) if plan['ready'] else None,
            'already_matches':plan['ready'] and not plan['writes'] and any(
                i['key']==page.get('state_metadata',{}).get('current_page_key') and i['status']=='complete'
                for i in page.get('state_metadata',{}).get('items',[])),
            'recommendations':plan['recommendations']})
    missing=[{'url':url,'label':label} for url,label in observed.items() if url not in seen]
    return {'schema':'application-coverage/1','system':target['system'],'target_id':target_id,
        'scope':'provided_observed_navigation_only','complete':not missing and bool(results) and all(p['ready_to_prepare'] for p in results),
        'observed_route_count':len(routes),'captured_page_count':len(results),
        'inspected_page_count':sum(p['observation_valid'] for p in results),
        'rejected_page_count':sum(not p['observation_valid'] for p in results),'uninspected_pages':missing,'pages':results,
        'profile_changed':False,'website_actions_performed':False,
        'limitation':'Completeness applies only to supplied observed routes; unseen conditional branches and record dialogs require inspection.'}
