"""Two-stage native UC term/grade filling; one durable canonical checkpoint.

School availability changes are deliberately separate. This workflow starts only
when the website already offers the observed Full/Semester course selectors.
"""
import copy
import re
from urllib.parse import urlsplit

from .browser import digest, structure, values, validate_observation, permission_gate, validate_uc_state
from .checkpoints import create_checkpoint, page_requirements, transaction_active
from .pages import resolve, encode
from .profile import ProfileError, _event, now
from .uc_courses import BASE, EDITOR, LABELS

TERMS=[('', '--'), ('F', 'Full'), ('S', 'Semester')]


def validate_native(page, context):
    """Accept only complete existing rows and their actual conditional grades."""
    validate_observation({k:v for k,v in page.items() if k not in {'state_metadata','uc_course_refill'}})
    match=re.fullmatch(EDITOR,urlsplit(page['url']).path)
    count=context.get('row_count')
    if (not match or not page['url'].startswith(BASE+'/') or urlsplit(page['url']).query
            or page['title']!='Enter HS classes - Academic history - UC application'
            or page.get('frames_present') or page.get('collections') or page.get('scope')
            or context.get('schema')!='uc-course-editor/1' or context.get('grade')!=match[1]
            or context.get('summary_url')!=BASE+'/my-application/acadHistFrGrades/'+match[1]
            or type(count) is not int or not 1<=count<=100
            or not re.fullmatch(r'\d{4} - \d{4} academic year',context.get('year',''))
            or not re.fullmatch(r'[a-f0-9]{64}',context.get('context_sha256',''))):
        raise ProfileError('observed_uc_refill_context_required')
    fields={f['key']:f for f in page['fields']};rows={i:{} for i in range(count)}
    for f in page['fields']:
        key=re.fullmatch(r'i:academics_hs_classes_add_(\d+)_(\w+)',f['key'])
        suffix=key[2] if key else None
        if (not key or int(key[1]) not in rows or suffix not in LABELS
                or f['label']!=LABELS[suffix] or f['disabled'] or f['readonly']
                or f['control']!=('text' if suffix in {'class_title','grade1Other','grade2Other'} else 'select')
                or f['selector']!='[id="'+f['key'][2:]+'"]'
                or f.get('selector_count',1)!=1 or f.get('selector_index',0)!=0):
            raise ProfileError('observed_uc_refill_controls_required')
        rows[int(key[1])][suffix]=f
    for row in rows.values():
        if not {'subject','class_title','honors','term'}<=set(row):
            raise ProfileError('existing_uc_refill_row_required')
        term=row['term']
        if [(o['value'],o['label']) for o in term['options']]!=TERMS or term['value'] not in {'','F','S'}:
            raise ProfileError('observed_uc_full_semester_choices_required')
        expected=0 if term['value']=='' else 1 if term['value']=='F' else 2
        for index in (1,2):
            if len(set(row)&{f'grade{index}',f'grade{index}Other'})!=int(index<=expected):
                raise ProfileError('observed_uc_conditional_grades_required')
        if any(f['invalid'] and f['key']!=term['key'] for f in row.values() if f['value']):
            raise ProfileError('unexplained_uc_refill_validation_error')
    actions=page['actions']
    if (len(actions)!=2 or {(a['key'],a['label']) for a in actions}!={('i:save','Save & continue'),('i:cancel-btn','Cancel')}
            or any(a['disabled'] or a['selector']!='[id="'+a['key'][2:]+'"]' for a in actions)):
        raise ProfileError('observed_uc_refill_save_cancel_required')
    return rows


def annotate(bundle):
    return {**bundle['page'],'uc_course_refill':{'schema':'uc-course-refill/1','context':bundle['summary']['context']},
            'state_metadata':bundle['state_metadata']}


def validate_bundle(bundle):
    if bundle.get('schema')!='uc-course-refill-bundle/1':raise ProfileError('uc_refill_bundle_required')
    rows=validate_native(bundle['page'],bundle['summary']['context'])
    parent=bundle['summary'].get('parent',{})
    if (parent.get('schema')!='uc-course-parent/1' or parent.get('context_sha256')!=bundle['summary']['context']['context_sha256']
            or parent.get('row_count')!=len(rows) or parent.get('url')!=bundle['summary']['context']['summary_url']
            or any(not re.fullmatch(r'[a-f0-9]{64}',value or '') for value in
                   (parent.get('summary_sha256'),bundle['summary'].get('rows_sha256')))):
        raise ProfileError('uc_refill_saved_parent_required')
    cells=bundle['summary'].get('cells',{})
    if (digest(cells)!=bundle['summary']['rows_sha256'] or len(cells.get('rows',[]))!=len(rows)
            or any(len(r)!=len(cells.get('columns',[])) for r in cells.get('rows',[]))
            or not {'Course name','Term','G1','G2'}<=set(cells.get('columns',[]))):
        raise ProfileError('uc_refill_saved_summary_cells_required')
    aux=bundle.get('auxiliary',{})
    if (aux.get('schema')!='uc-empty-comments/1' or aux.get('page_url')!=BASE+'/my-application/acadHistAddInformation'
            or aux.get('values_sha256')!=digest({'i:additional_comments':''})
            or not re.fullmatch(r'[a-f0-9]{64}',aux.get('structure_sha256',''))):
        raise ProfileError('uc_refill_empty_comments_baseline_required')
    validate_uc_state(bundle['state_metadata'],annotate(bundle))
    return rows


def _requirements(profile,target,bundle):
    rows=validate_bundle(bundle);bindings=target.get('page_field_bindings',{}).get(urlsplit(bundle['page']['url']).path,{})
    facts=['education.uc_ap_reporting_term','education.uc_other_settings_retained'];courses=[];columns={};desired=[]
    if (profile['facts'].get(facts[0],{}).get('value')!='Full year'
            or profile['facts'].get(facts[1],{}).get('value') is not True):
        raise ProfileError('explicit_uc_refill_reporting_choices_required')
    for index,row in rows.items():
        def supplied(key):
            ref=bindings.get(key)
            if not ref:raise ProfileError('explicit_page_scoped_uc_refill_binding_required')
            value,ids=resolve(profile,ref);courses.extend(ids)
            if ids:
                record,column=ref[4:].rsplit(':',1);columns.setdefault(record,[]).append(column)
            else:facts.append(ref)
            return ref,value
        title_ref,title=supplied(row['class_title']['key'])
        if not title_ref.startswith('psr:') or not title_ref.endswith(':description') or re.sub(r'\s+',' ',str(title)).strip().casefold()!=row['class_title']['value'].strip().casefold():
            raise ProfileError('matching_original_psr_course_required')
        for suffix in ('subject','honors','subject_language_code','grade_system'):
            if suffix in row:
                _,value=supplied(row[suffix]['key'])
                if encode(row[suffix],value)!=row[suffix]['value']:
                    raise ProfileError('unconfirmed_uc_classification_change')
        ref,term=supplied(row['term']['key']);encoded=encode(row['term'],term)
        if encoded not in {'F','S'} or (row['honors']['value']=='AP' and encoded!='F'):
            raise ProfileError('explicit_uc_row_term_required')
        grades=[]
        for j in range(1,2 if encoded=='F' else 3):
            # Use the already observed naming variant for Other scales. For
            # newly exposed controls the supported percentage variant is bound
            # explicitly; no grade is derived from a completion date or scale.
            key=f'i:academics_hs_classes_add_{index}_grade{j}'
            if key not in bindings:key+='Other'
            gref,grade=supplied(key)
            if not gref.startswith('psr:') and str(grade) not in {'NO','IP','PL'}:
                raise ProfileError('psr_original_grade_or_confirmed_status_required')
            if gref.startswith('psr:') and (gref[4:].rsplit(':',1)[0]!=title_ref[4:].rsplit(':',1)[0]
                    or not gref.endswith((':school_percent',':school_grade_symbol',':final_result'))):
                raise ProfileError('same_course_original_grade_required')
            grades.append({'field_key':key,'fact_ref':gref,'supplied':grade})
        desired.append({'row':index,'field_key':row['term']['key'],'fact_ref':ref,'value':encoded,'grades':grades})
    gate=page_requirements(profile,fact_ids=list(dict.fromkeys(facts)),course_ids=list(dict.fromkeys(courses)),record_columns=columns)
    if not gate['data_ready']:raise ProfileError('uc_refill_source_gate_failed')
    return desired,gate,list(dict.fromkeys(facts)),list(dict.fromkeys(courses)),columns


def prepare_refill(profile,target_id,bundle,context,*,reaffirm_term_keys=None):
    if any(transaction_active(cp) for cp in profile['checkpoints'].values()):raise ProfileError('pending_transaction_requires_recovery')
    target=profile['targets'].get(target_id,{})
    if target.get('system')!='uc':raise ProfileError('student_selected_uc_target_required')
    rows,gate,facts,courses,columns=_requirements(profile,target,bundle)
    reaffirm=set(reaffirm_term_keys or [])
    if not reaffirm<={row['field_key'] for row in rows}:raise ProfileError('observed_uc_term_reaffirmation_required')
    permission_gate(context,annotate(bundle),BASE)
    if context.get('real_account_test') and context['restoration_strategy']['baseline_parent_sha256']!=digest(bundle['summary']['parent']):
        raise ProfileError('observed_uc_refill_restoration_evidence_required')
    if context.get('real_account_test') and any(f['value']=='' for f in bundle['page']['fields']):
        raise ProfileError('real_refill_test_requires_complete_original_values')
    checkpoint=create_checkpoint(profile,target_id,bundle['page']['url']+'#term-refill',fact_ids=facts,course_ids=courses,record_columns=columns)
    plan={'schema':'uc-course-refill-plan/1','ready':True,'checkpoint_id':checkpoint,'system':'uc','allowed_origin':BASE,
        'page_url':bundle['page']['url'],'bundle_sha256':digest(bundle),'rows':rows,
        'writes':[{k:r[k] for k in ('field_key','fact_ref','value')} for r in rows
                  if values(bundle['page'])[r['field_key']]!=r['value'] or r['field_key'] in reaffirm],
        'context':copy.deepcopy(bundle['summary']['context']),'original_values_sha256':digest(values(bundle['page']))}
    profile['checkpoints'][checkpoint].update(kind='uc_course_refill',state='prepared',journal=copy.deepcopy(bundle),
        prepared_plan=copy.deepcopy(plan),context=copy.deepcopy(context),source_gate=gate,prepared_at=now())
    _event(profile,'uc_course_refill_prepared',[checkpoint])
    return plan


def _checkpoint(profile,checkpoint):
    cp=profile['checkpoints'].get(checkpoint,{})
    if cp.get('kind')!='uc_course_refill' or cp.get('journal') is None or not transaction_active(cp):
        raise ProfileError('prepared_uc_refill_checkpoint_required')
    return cp


def prepare_grades(profile,checkpoint,page,*,restoration=False):
    cp=_checkpoint(profile,checkpoint);original=cp['journal'];plan=cp['prepared_plan'];rows=validate_native(page,plan['context'])
    if page['url']!=plan['page_url']:raise ProfileError('uc_refill_page_changed')
    initial={f['key']:f for f in original['page']['fields']};current={f['key']:f for f in page['fields']}
    if restoration:
        expected=values(original['page'])
        if digest(structure(page))!=digest(structure(original['page'])):
            raise ProfileError('uc_refill_original_shape_not_restored')
    else:
        expected={k:f['value'] for k,f in initial.items() if not re.search(r'_grade[12](Other)?$',k)}
        expected.update({r['field_key']:r['value'] for r in plan['rows']})
        wanted=set(expected)|{g['field_key'] for r in plan['rows'] for g in r['grades']}
        if set(current)!=wanted:raise ProfileError('unknown_conditional_uc_refill_fields')
        for key,value in expected.items():
            if current[key]['value']!=value or structure({**page,'fields':[current[key]]})['fields']!=structure({**original['page'],'fields':[initial[key]]})['fields']:
                raise ProfileError('retained_uc_refill_fields_changed')
        for r in plan['rows']:
            for g in r['grades']:expected[g['field_key']]=encode(current[g['field_key']],g['supplied'])
    writes=[{'field_key':key,'value':value} for key,value in expected.items() if current[key]['value']!=value]
    if any(not re.search(r'_grade[12](Other)?$',w['field_key']) for w in writes):
        raise ProfileError('uc_refill_grade_phase_only')
    grade_plan={**copy.deepcopy(plan),'schema':'uc-course-grade-plan/1','restoration':restoration,
        'observation_sha256':digest(page),'structure_sha256':digest(structure(page)),
        'writes':writes,'expected_values_sha256':digest(expected),'save_action':next(a for a in page['actions'] if a['key']=='i:save')}
    cp['grade_plan']=copy.deepcopy(grade_plan);cp['state']='prepared';_event(profile,'uc_course_grades_prepared',[checkpoint])
    return grade_plan


def recover_refill(profile,checkpoint):
    cp=_checkpoint(profile,checkpoint);plan=cp['prepared_plan'];original=cp['journal']
    return {'plan':copy.deepcopy(plan),'grade_plan':copy.deepcopy(cp.get('grade_plan')),
        'context':{**copy.deepcopy(cp['context']),'journal_persisted':True},'original':copy.deepcopy(original),
        'term_writes':[{'field_key':f['key'],'value':f['value']} for f in original['page']['fields'] if f['key'].endswith('_term')]}


def verify_refill(profile,checkpoint,bundle,*,revisited_after_save,restoration=False):
    cp=_checkpoint(profile,checkpoint);validate_bundle(bundle);original=cp['journal'];grade=cp.get('grade_plan',{})
    expected=digest(values(original['page'])) if restoration else grade.get('expected_values_sha256')
    page=bundle['page'];valid=(revisited_after_save is True and page['url']==original['page']['url']
        and digest(values(page))==expected and (restoration or not any(f['invalid'] for f in page['fields']))
        and bundle['summary']['context']['context_sha256']==original['summary']['context']['context_sha256']
        and bundle['auxiliary']==original['auxiliary'])
    if restoration:
        valid=valid and digest(structure(page))==digest(structure(original['page'])) and bundle==original
    else:
        valid=valid and digest(structure(page))==grade.get('structure_sha256')
        cells=bundle['summary']['cells'];fields={f['key']:f for f in page['fields']}
        for row in cp['prepared_plan']['rows']:
            index=row['row'];prefix=f'i:academics_hs_classes_add_{index}_';saved=cells['rows'][index]
            term=fields[prefix+'term']['value']
            valid=valid and saved[cells['columns'].index('Course name')]==fields[prefix+'class_title']['value']
            valid=valid and saved[cells['columns'].index('Term')]==('Full' if term=='F' else 'Semester')
            for j in (1,2):
                field=fields.get(prefix+f'grade{j}',fields.get(prefix+f'grade{j}Other'))
                display='' if field is None else field['value'] if field['control']=='text' else next((o['label'] for o in field['options'] if o['value']==field['value']),None)
                valid=valid and saved[cells['columns'].index('G'+str(j))]==display
        # Compare the complete saved review tree during tests. An ordinary refill
        # may complete its own grade/comments/review, never another section.
        before=original['state_metadata'];after=bundle['state_metadata']
        if cp['context'].get('real_account_test'):valid=valid and before==after
        else:
            for b,a in zip(before['sections'],after['sections']):
                if b['label']!='Academic history':valid=valid and b==a
                else:
                    allowed={urlsplit(grade['context']['summary_url']).path,'/my-application/acadHistAddInformation','/my-application/acadHistReview'}
                    valid=valid and [i for i in b['pages'] if i['href'] not in allowed]==[i for i in a['pages'] if i['href'] not in allowed]
                    current={i['href']:i['label'] for i in a['pages']}
                    valid=valid and current.get(urlsplit(grade['context']['summary_url']).path)=='Edit grade'
                    valid=valid and current.get('/my-application/acadHistAddInformation')=='Edit Additional information'
                    if b['completion_text']=='Section Complete':valid=valid and a['completion_text']=='Section Complete'
    cp['state']='restored' if valid and restoration else 'verified' if valid else 'needs_restore'
    if valid and (restoration or not cp['context'].get('real_account_test')):
        cp['verified_values_sha256']=digest(values(page));cp['verified_state_sha256']=digest(bundle['state_metadata'])
        cp['journal']=None;cp.pop('prepared_plan',None);cp.pop('grade_plan',None)
    _event(profile,'uc_refill_restored' if valid and restoration else 'uc_refill_checked',[checkpoint])
    return {'verified':bool(valid),'restored':bool(valid and restoration),'state':cp['state']}
