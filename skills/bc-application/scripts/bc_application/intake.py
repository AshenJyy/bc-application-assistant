"""One read-only factual collection agenda across observed application targets."""
from .browser import digest
from .coverage import inventory
from .checkpoints import transaction_active
from .profile import ProfileError


def agenda(profile,requests):
    if (not isinstance(requests,list) or not 1<=len(requests)<=25 or any(not isinstance(r,dict) or
            set(r)!={'target_id','pages','routes'} or not isinstance(r['pages'],list) or not isinstance(r['routes'],list)
            or any(not isinstance(p,dict) for p in r['pages']) for r in requests)
            or sum(len(r['pages']) for r in requests)>250 or sum(len(r['routes']) for r in requests)>250):
        raise ProfileError('bounded_observed_collection_requests_required')
    target_ids=[r['target_id'] for r in requests]
    if any(not isinstance(i,str) for i in target_ids) or len(set(target_ids))!=len(target_ids):
        raise ProfileError('unique_collection_target_requests_required')
    if any(i not in profile['targets'] for i in target_ids):raise ProfileError('student_selected_target_required')
    identity={'schema':'collection-agenda/1','scope':'provided_observed_navigation_only',
        'profile_id':profile['profile_id'],'profile_revision':profile['revision'],'profile_sha256':digest(profile),
        'observation_set_sha256':digest([{'target_id':r['target_id'],'routes':r['routes'],
            'pages':[{'url':p.get('url'),'sha256':digest(p)} for p in r['pages']]} for r in requests]),
        'profile_changed':False,'website_actions_performed':False,'execution_verified':False}
    recovery=[{'checkpoint_id':key,'target_id':cp['target_id'],'page_url':cp['page_key'],'state':cp['state']}
        for key,cp in profile['checkpoints'].items() if transaction_active(cp)]
    if recovery:return {**identity,'recovery_required':recovery,'questions':[],'question_groups':[],
        'complete':False,'inspection_deferred':True,'limitation':'Resolve the existing transaction before collecting more answers or preparing another page.'}
    reports=[inventory(profile,r['target_id'],r['pages'],r['routes']) for r in requests]
    required={};questions={};source_reviews={};academic_reviews={};manual=[];gaps=[];ready=[];matched=[];uninspected=[];recommendations=[];blocked=[]
    for report in reports:
        system=report['system'];target=report['target_id']
        uninspected.extend({'target_id':target,'system':system,**r} for r in report['uninspected_pages'])
        for page in report['pages']:
            use={'target_id':target,'system':system,'page_url':page['page_url'],'page_label':page['label']}
            for ref in page['required_fact_ids']:
                related=[f['label'] for f in page['fields'] if f['fact_ref']==ref]
                item={**use,'field_labels':list(dict.fromkeys(related))}
                required.setdefault(ref,[]).append(item)
            for reason,key in [('missing','missing_fact_ids'),('conflict','conflicted_fact_ids')]:
                for ref in page[key]:
                    entry=questions.setdefault(ref,{'fact_id':ref,'reason':reason,'uses':[]})
                    if reason=='conflict':entry['reason']='conflict'
                    if use not in entry['uses']:entry['uses'].append(use)
            for review in page['source_issues']:
                key=digest(review);source_reviews.setdefault(key,{'issue':review,'uses':[]})['uses'].append(use)
            for review in page['academic_reviews']:
                key=digest(review);academic_reviews.setdefault(key,{'review':review,'uses':[]})['uses'].append(use)
            if page['manual_fields']:manual.append({**use,'field_keys':page['manual_fields']})
            other=[b for b in page['blockers'] if b['reason']!='page_data_gate_failed' and b.get('field_key') not in {
                f['field_key'] for f in page['fields'] if f['fact_ref'] in page['missing_fact_ids']+page['conflicted_fact_ids']}]
            if other:
                blocked.append({**use,'blockers':other})
                structural=[b for b in other if b['reason'].startswith(('observed_','unmapped_','repeatable_','frames_','conditional_'))
                    or 'unsupported' in b['reason'] or 'not_supported' in b['reason']]
                if structural:gaps.append({**use,'blockers':structural})
            if page['ready_to_prepare']:
                item={**use,'observation_sha256':page['observation_sha256'],'planned_write_count':page['planned_write_count']}
                if page['already_matches']:item['saved_revisit_required']=True
                (matched if page['already_matches'] else ready).append(item)
            for recommendation in page['recommendations']:
                entry={**use,**recommendation}
                if entry not in recommendations:recommendations.append(entry)
    groups={}
    for ref,item in sorted(questions.items()):
        parts=ref.split('.')
        group='personal.languages' if ref.startswith('personal.languages.') else '.'.join(parts[:-1]) if len(parts)>2 else parts[0]
        groups.setdefault(group,[]).append(ref)
        item['field_labels']=list(dict.fromkeys(label for use in required.get(ref,[]) for label in use['field_labels']))
    known=[ref for ref in sorted(required) if ref in profile['facts'] and ref not in questions]
    return {**identity,'recovery_required':[],'inspection_deferred':False,
        'questions':[questions[k] for k in sorted(questions)],
        'question_groups':[{'group':k,'fact_ids':v} for k,v in sorted(groups.items())],
        'known_fact_ids':known,'known_fact_count':len(known),'required_fact_count':len(required),
        'required_uses_count':sum(len(uses) for uses in required.values()),
        'ready_pages':ready,'already_matching_pages':matched,'manual_pages':manual,'implementation_gaps':gaps,
        'other_page_blockers':blocked,
        'source_reviews':list(source_reviews.values()),'academic_reviews':list(academic_reviews.values()),
        'uninspected_pages':uninspected,'optional_recommendations':recommendations,
        'observed_route_count':sum(r['observed_route_count'] for r in reports),
        'captured_page_count':sum(r['captured_page_count'] for r in reports),
        'complete':all(r['complete'] for r in reports),'profile_changed':False,'website_actions_performed':False,
        'limitation':'Readiness is not saved completion. Matching pages need an independent saved-draft revisit before completion; do not discard unsaved current-page edits. Questions contain only mapped required factual gaps. No writes or saves are performed by this agenda.'}
