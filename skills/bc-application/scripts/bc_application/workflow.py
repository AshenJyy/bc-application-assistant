"""Derived, read-only coordination for supported Common App academic pages.

No second applicant state: source reports and per-page journals remain canonical.
This does not discover university application routes or certify full coverage.
"""
from urllib.parse import urlsplit

from . import academic,schools
from .browser import digest,origin
from .checkpoints import transaction_active
from .profile import ProfileError

PATHS={'/common/4/18':('common_school','current',0),'/common/4/19':('common_school','other',1),
    '/common/13/55':('common_academic','9',2),'/common/13/56':('common_academic','10',3),'/common/13/57':('common_academic','11',4)}
ORIGINS={schools.ORIGIN,'http://127.0.0.1:8765','http://localhost:8765'}


def agenda(profile,steps,routes):
    if (not isinstance(steps,list) or not 1<=len(steps)<=25 or not isinstance(routes,list) or not 1<=len(routes)<=100):
        raise ProfileError('bounded_observed_workflow_required')
    witnesses={}
    for r in routes:
        if (not isinstance(r,dict) or set(r)!={'url','label'} or not isinstance(r['label'],str) or not r['label'].strip()):
            raise ProfileError('observed_workflow_route_required')
        u=urlsplit(r['url'])
        if origin(r['url']) not in ORIGINS or u.query or u.fragment:raise ProfileError('supported_workflow_origin_required')
        if r['url'] in witnesses and witnesses[r['url']]!=r['label']:raise ProfileError('conflicting_workflow_route')
        witnesses[r['url']]=r['label']
    jobs={};origins=set()
    for step in steps:
        if not isinstance(step,dict) or set(step)!={'target_id','kind','report_ref','page_url'}:raise ProfileError('workflow_step_schema_required')
        target=step['target_id'];url=step['page_url'];u=urlsplit(url);spec=PATHS.get(u.path)
        if profile['targets'].get(target,{}).get('system')!='common_app':raise ProfileError('student_selected_common_target_required')
        if url not in witnesses or not spec or step['kind']!=spec[0] or origin(url) not in ORIGINS or u.query or u.fragment:
            raise ProfileError('observed_supported_workflow_page_required')
        schools.fact_ref(step['report_ref']);origins.add(origin(url))
        if url in jobs:
            if jobs[url]['report_ref']!=step['report_ref']:raise ProfileError('shared_application_page_requires_one_report')
            if target not in jobs[url]['target_ids']:jobs[url]['target_ids'].append(target)
        else:jobs[url]={k:step[k] for k in ('kind','report_ref','page_url')}|{'job_id':digest([url,step['report_ref']]),
            'target_id':target,'target_ids':[target],'label':witnesses[url],'order':spec[2],'expected_kind':spec[1]}
    if len(origins)!=1:raise ProfileError('one_workflow_browser_origin_required')
    jobs=sorted(jobs.values(),key=lambda j:j['order'])
    identity={'schema':'common-academic-workflow/1','scope':'provided_supported_common_app_pages_only',
        'profile_id':profile['profile_id'],'profile_revision':profile['revision'],'profile_sha256':digest(profile),
        'request_sha256':digest({'steps':steps,'routes':routes}),'profile_changed':False,'website_actions_performed':False,
        'full_application_complete':False}
    recovery=[]
    for key,cp in profile['checkpoints'].items():
        if transaction_active(cp):
            job=next((j for j in jobs if j['page_url']==cp['page_key'] and j['report_ref']==cp.get('report_ref') and cp['target_id'] in j['target_ids']),None)
            recovery.append({'checkpoint_id':key,'page_url':cp['page_key'],'target_id':cp['target_id'],'kind':cp.get('kind'),
                'job_id':job['job_id'] if job else None,'context':cp.get('context'),
                'original_values_sha256':digest(cp['journal']) if cp.get('journal') is not None else None,
                **({'original_parent':cp['original_parent']} if cp.get('kind')=='common_academic_creation' else {})})
    if recovery:return {**identity,'ready':False,'jobs':jobs,'recovery_required':recovery,'questions':[],
        'known_fact_ids':[],'source_reviews':[],'implementation_gaps':[],'directory_discovery':[],'inspection_deferred':True}
    questions={};known=set();required=set();reviews=[];gaps=[];discovery={};compiled=[]
    for job in jobs:
        ref=job['report_ref'];compiler=schools.compile_report if job['kind']=='common_school' else academic.compile_report
        try:c=compiler(profile,ref)
        except ProfileError as exc:
            gaps.append({'job_id':job['job_id'],'reason':str(exc)});job['source_ready']=False;continue
        if c.get('kind',c.get('grade')) not in {None,job['expected_kind']}:raise ProfileError('workflow_report_page_mismatch')
        gate=c['source_gate'];required.update(c['required_fact_ids'])
        missing=gate['missing_fact_ids'];conflicted=gate['conflicted_fact_ids']
        if ref in missing:gaps.append({'job_id':job['job_id'],'reason':'source_reference_report_needs_implementation','report_ref':ref})
        for reason,refs in [('missing',missing),('conflict',conflicted)]:
            for fact in refs:
                if fact==ref:continue  # A report is agent implementation, not a student's answer.
                q=questions.setdefault(fact,{'fact_id':fact,'reason':reason,'job_ids':[],'target_ids':[]})
                if reason=='conflict':q['reason']=reason
                if job['job_id'] not in q['job_ids']:q['job_ids'].append(job['job_id'])
                q['target_ids']=list(dict.fromkeys(q['target_ids']+job['target_ids']))
        known.update(f for f in c['required_fact_ids'] if f in profile['facts'] and f not in conflicted)
        issues=[*gate['source_issues'],*gate['academic_reviews']]
        reviews.extend({'job_id':job['job_id'],'issue':issue} for issue in issues)
        blockers=[b for b in c.get('blockers',[]) if b.get('ref') not in missing+conflicted]
        if blockers:gaps.append({'job_id':job['job_id'],'reason':'source_report_blocked','blockers':blockers})
        for lookup in c.get('lookups_needed',[]):discovery.setdefault(lookup['psr_school_id'],lookup)
        job.update(source_ready=gate['data_ready'] and not c.get('blockers'),source_fingerprint=c.get('source_fingerprint'))
        compiled.append((job,c))
    # A fresh academic workflow must establish the schools it references first.
    school_jobs={j['expected_kind'] for j in jobs if j['kind']=='common_school'}
    academic_jobs=[j for j in jobs if j['kind']=='common_academic']
    if academic_jobs and school_jobs!={'current','other'}:
        gaps.append({'reason':'school_pages_required_before_academic_workflow'})
    registered={s['psr_school_id'] for j,c in compiled if j['kind']=='common_school' for s in c.get('schools',[])}
    for job,c in compiled:
        if job['kind']!='common_academic' or not c.get('ready'):continue
        report=profile['facts'][job['report_ref']]['value']
        for row in report['transcripts']:
            key=row['psr_school_id'];cached=profile.get('school_directory',{}).get('entries',{}).get(key,{}).get('common_app')
            if key not in registered:gaps.append({'job_id':job['job_id'],'reason':'academic_school_not_in_school_reports','psr_school_id':key})
            elif cached:
                label=profile['facts'][row['header_refs']['school_name']]['value']
                if schools.name_key(label)!=schools.name_key(cached['name']):gaps.append({'job_id':job['job_id'],'reason':'academic_school_directory_name_conflict'})
    fingerprint=digest({'profile_id':profile['profile_id'],'academic_sha256':profile['academic_sha256'],
        'jobs':[{k:j.get(k) for k in ('job_id','source_fingerprint','target_ids')} for j in jobs],
        'targets':{t:profile['targets'][t] for j in jobs for t in j['target_ids']}})
    return {**identity,'ready':not(questions or reviews or gaps) and all(j['source_ready'] for j in jobs),
        'inspection_deferred':False,'recovery_required':[],'jobs':jobs,'questions':[questions[k] for k in sorted(questions)],
        'known_fact_ids':sorted(known-questions.keys()),'required_fact_count':len(required),
        'source_reviews':reviews,'implementation_gaps':gaps,'directory_discovery':list(discovery.values()),
        'source_set_sha256':fingerprint,'limitation':'Source readiness is not website completion. Each page still requires actual observation, a persisted journal and independent saved verification. No full-application claim.'}
