"""PSR school/enrollment references and reusable public directory identities."""
import copy
import re
from datetime import date

from .browser import digest,permission_gate
from .checkpoints import page_requirements,transaction_active
from .pages import resolve
from .profile import ProfileError,_event,now

ORIGIN='https://apply.commonapp.org'
PATHS={'/common/4/18','/common/4/19'}
STATEMENTS={'current':'education.explanations.school_progression','other':'education.explanations.school_transfer'}
PROGRESSION={'early','late','time_off','gap_year','unchanged'}
MONTHS=('January','February','March','April','May','June','July','August','September','October','November','December')


def school(profile,key):
    result=next((s for s in profile['academic']['schools'] if s['school_id']==key),None)
    if result is None:raise ProfileError('original_psr_school_required')
    return result


def name_key(value):
    if not isinstance(value,str):raise ProfileError('public_school_name_required')
    return re.sub(r'\s+',' ',re.sub(r'^\s*\d+\s*[-–]\s*','',value)).strip().casefold()


def validate_directory(profile):
    data=profile.get('school_directory',{'schema':'school-directory/1','entries':{}})
    if set(data)!={'schema','entries'} or data['schema']!='school-directory/1' or not isinstance(data['entries'],dict):
        raise ProfileError('school_directory_schema_required')
    for key,systems in data['entries'].items():
        original=school(profile,key)
        if set(systems)!={'common_app'}:raise ProfileError('observed_school_directory_system_required')
        entry=systems['common_app']
        if (set(entry)!={'name','city','region','country','ceeb','evidence'}
                or name_key(entry['name'])!=name_key(original['district_school_name_raw'])
                or not isinstance(entry['city'],str) or not entry['city'].strip()
                or entry['region']!='BC' or entry['country']!='Canada'
                or not isinstance(entry['ceeb'],str) or not re.fullmatch(r'\d{6}',entry['ceeb'])):
            raise ProfileError('source_backed_bc_school_identity_required')
        from urllib.parse import urlsplit
        ev=entry['evidence'];u=urlsplit(ev.get('page_url',''))
        if (set(ev)!={'page_url','query','search_by','results_sha256','observed_at','match_kind'}
                or u.scheme+'://'+u.netloc not in {ORIGIN,'http://localhost:8765','http://127.0.0.1:8765'}
                or u.path not in PATHS or u.query or u.fragment
                or name_key(ev['query'])!=name_key(original['district_school_name_raw'])
                or ev['search_by']!='High School Name' or ev['match_kind']!='exact_psr_name_bc_canada'
                or not re.fullmatch(r'[a-f0-9]{64}',ev['results_sha256']) or not isinstance(ev['observed_at'],str)):
            raise ProfileError('public_school_identity_evidence_required')


def resolve_lookup(profile,school_id,lookup):
    """No write: accept a unique match only from the complete visible result set."""
    original=school(profile,school_id)
    gate=page_requirements(profile,fact_ids=[])
    if not gate['data_ready']:return {'ready':False,'source_gate':gate,'website_actions_performed':False}
    from .common_schools import validate_lookup
    validate_lookup(lookup)
    if lookup['search_by']!='High School Name' or name_key(lookup['query'])!=name_key(original['district_school_name_raw']):
        raise ProfileError('psr_school_name_search_required')
    options=[o for o in lookup['options'] if o['kind']=='school']
    matches=[o for o in options if name_key(o['name'])==name_key(original['district_school_name_raw']) and o['region']=='BC' and o['country']=='Canada']
    if lookup['total']!=len(options):
        return {'ready':False,'reason':'school_search_results_incomplete','website_actions_performed':False}
    if len(matches)!=1:return {'ready':False,'reason':'school_identity_ambiguous_or_not_found','matches':len(matches),'website_actions_performed':False}
    selected=matches[0]
    identity={k:selected[k] for k in ('name','city','region','country','ceeb')}
    identity['evidence']={'page_url':lookup['page_url'],'query':lookup['query'],'search_by':lookup['search_by'],
        'results_sha256':digest(lookup['options']),'observed_at':now(),'match_kind':'exact_psr_name_bc_canada'}
    return {'ready':True,'psr_school_id':school_id,'identity':identity,'website_actions_performed':False}


def remember_lookup(profile,school_id,lookup,context):
    if any(transaction_active(c) for c in profile['checkpoints'].values()):raise ProfileError('pending_transaction_requires_recovery')
    permission_gate(context,{'url':lookup['page_url']},ORIGIN)
    gate=page_requirements(profile,fact_ids=[])
    if not gate['data_ready']:return {'ready':False,'source_gate':gate,'profile_changed':False}
    result=resolve_lookup(profile,school_id,lookup)
    if not result['ready']:return {**result,'profile_changed':False}
    old=profile.get('school_directory',{}).get('entries',{}).get(school_id,{}).get('common_app')
    if old and any(old[k]!=result['identity'][k] for k in ('name','city','region','country','ceeb')):
        raise ProfileError('conflicting_school_directory_identity_requires_review')
    if old:return {**result,'profile_changed':False,'reused':True}
    profile.setdefault('school_directory',{'schema':'school-directory/1','entries':{}})['entries'][school_id]={'common_app':copy.deepcopy(result['identity'])}
    validate_directory(profile);_event(profile,'public_school_identity_recorded',[school_id])
    return {**result,'profile_changed':True,'reused':False}


def fact_ref(ref):
    from .profile import FACT_ID
    if not isinstance(ref,str) or not FACT_ID.fullmatch(ref) or not ref.startswith('education.'):
        raise ProfileError('explicit_school_fact_reference_required')


def month(value):
    if not isinstance(value,str):raise ProfileError('explicit_school_month_required')
    try:
        if re.fullmatch(r'\d{4}-\d{2}(?:-\d{2})?',value):parsed=date.fromisoformat(value+'-01' if len(value)==7 else value)
        elif re.fullmatch(r'\d{1,2}-[A-Za-z]{3}-\d{4}',value):
            day,short,year=value.split('-');index=next((i for i,name in enumerate(MONTHS,1) if name[:3].casefold()==short.casefold()),0)
            parsed=date(int(year),index,int(day))
        else:raise ValueError()
    except ValueError as exc:raise ProfileError('explicit_school_month_required') from exc
    # Fixed English labels independent of the host locale; retain the raw day in PSR.
    return f'{MONTHS[parsed.month-1]} {parsed.year}'


def compile_report(profile,report_ref):
    fact_ref(report_ref);required=[report_ref];blockers=[];lookups=[]
    def fact(ref):
        fact_ref(ref);required.append(ref)
        try:return resolve(profile,ref)[0]
        except ProfileError:return None
    report=profile['facts'].get(report_ref,{}).get('value')
    if report is None:return {'ready':False,'required_fact_ids':required,'source_gate':page_requirements(profile,fact_ids=required),'blockers':[],'lookups_needed':[]}
    keys={'schema','kind','current_school_ref','schools','boarding_ref','graduate_ref','graduation_ref','progression_ref','explanation_ref'}
    if (not isinstance(report,dict) or set(report)!=keys or report['schema']!='school-report/1' or report['kind'] not in {'current','other'}
            or not isinstance(report['schools'],list) or len(report['schools'])>(1 if report['kind']=='current' else 3)
            or (report['kind']=='current' and len(report['schools'])!=1)):
        raise ProfileError('explicit_school_report_schema_required')
    current=fact(report['current_school_ref'])
    if current is not None:school(profile,current)
    rows=[];seen=set()
    def enrollment_date(ref,key,column):
        original=school(profile,key)
        raw=[e['raw_cells'].get(column,'') for e in original['enrollments']]
        if isinstance(ref,str) and ref.startswith('psr-school:'):
            match=re.fullmatch(r'psr-school:([^:]+):(\d+):(admit_date|withdrawal_date)',ref)
            if not match or match[1]!=key or match[3]!=column:raise ProfileError('original_enrollment_reference_required')
            try:value=raw[int(match[2])]
            except IndexError as exc:raise ProfileError('original_enrollment_reference_required') from exc
        else:
            value=fact(ref)
            if value is None:return None
            recorded=[month(v) for v in raw if v]
            if recorded and month(value) not in recorded:raise ProfileError('original_school_date_conflict')
            if not recorded:
                kinds={profile['sources'][s]['kind'] for s in profile['facts'][ref]['source_refs']}
                if not ('student_statement' in kinds and kinds&{'transcript','report_card'}):
                    blockers.append({'reason':'missing_school_date_requires_transcript_and_clarification','fact_ref':ref})
        if not value:
            blockers.append({'reason':'original_school_date_missing','psr_school_id':key,'column':column});return None
        return month(value)
    validate_directory(profile)
    for item in report['schools']:
        if not isinstance(item,dict) or set(item)!={'psr_school_id','entry_ref','exit_ref'}:raise ProfileError('original_school_report_row_required')
        key=item['psr_school_id'];school(profile,key)
        if key in seen or current is not None and (report['kind']=='current')!=(key==current):
            raise ProfileError('school_role_or_duplicate_conflict')
        seen.add(key)
        identity=profile.get('school_directory',{}).get('entries',{}).get(key,{}).get('common_app')
        if identity is None:lookups.append({'psr_school_id':key,'query':re.sub(r'^\s*\d+\s*[-–]\s*','',school(profile,key)['district_school_name_raw']).strip()})
        row={'psr_school_id':key,'identity':copy.deepcopy(identity),'entry':enrollment_date(item['entry_ref'],key,'admit_date')}
        if report['kind']=='other':
            row['exit']=enrollment_date(item['exit_ref'],key,'withdrawal_date')
            def order(v):
                name,year=v.split();return int(year),MONTHS.index(name)
            if row['entry'] and row['exit'] and order(row['entry'])>order(row['exit']):
                raise ProfileError('school_enrollment_date_order_conflict')
        elif item['exit_ref'] is not None:raise ProfileError('current_school_exit_not_requested')
        rows.append(row)
    compiled={'kind':report['kind'],'schools':rows}
    explanation_needed=bool(rows) if report['kind']=='other' else False;explanation_unknown=False
    if report['kind']=='current':
        boarding=fact(report['boarding_ref']);graduate=fact(report['graduate_ref']);progress=fact(report['progression_ref'])
        compiled.update(boarding=boarding,graduate=graduate,progression=progress)
        explanation_unknown=progress is None
        if boarding is not None and type(boarding) is not bool:blockers.append({'reason':'explicit_school_boarding_answer_required'})
        if graduate is not True:blockers.append({'reason':'school_non_graduate_branch_unimplemented' if graduate is False else 'explicit_school_graduation_answer_required'})
        graduation=fact(report['graduation_ref']);compiled['graduation']=month(graduation) if graduation is not None else None
        if progress is not None:
            if (not isinstance(progress,list) or not progress or any(p not in PROGRESSION for p in progress) or len(set(progress))!=len(progress)
                    or 'unchanged' in progress and len(progress)!=1 or {'early','late'}<=set(progress)):
                blockers.append({'reason':'explicit_complete_school_progression_list_required'})
            else:explanation_needed=progress!=['unchanged']
    elif any(report[k] is not None for k in ('boarding_ref','graduate_ref','graduation_ref','progression_ref')):
        raise ProfileError('school_report_kind_fields_conflict')
    compiled['explanation']=None
    if explanation_needed:
        if report['explanation_ref']!=STATEMENTS[report['kind']]:raise ProfileError('scoped_factual_school_explanation_required')
        text=fact(report['explanation_ref'])
        if text is not None:
            source=profile['facts'][report['explanation_ref']]
            if (not isinstance(text,str) or not 1<=len(text.split())<=250 or '<' in text or '>' in text
                    or not any(profile['sources'][s]['kind']=='student_statement' for s in source['source_refs'])):
                blockers.append({'reason':'student_supplied_factual_school_explanation_required'})
            else:compiled['explanation']=' '.join(text.split())
    elif report['explanation_ref'] is not None and not explanation_unknown:raise ProfileError('unneeded_school_explanation_must_remain_unbound')
    required=list(dict.fromkeys(required));gate=page_requirements(profile,fact_ids=required)
    return {**compiled,'ready':gate['data_ready'] and not blockers and not lookups,'source_ready':gate['data_ready'] and not blockers,
        'required_fact_ids':required,'source_gate':gate,'blockers':blockers,'lookups_needed':lookups,
        'source_fingerprint':digest({'academic_sha256':profile['academic_sha256'],'facts':{r:profile['facts'].get(r) for r in required},
            'identities':{r['psr_school_id']:r['identity'] for r in rows}})}
