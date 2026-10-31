"""UC term-availability preflight and durable school/course test recovery.

Changing the school's allowed terms is distinct from assigning a course's term.
The preview cannot authorize input; preparation persists all original snapshots.
"""
import copy
import re
from urllib.parse import parse_qs, urlsplit

from .browser import digest, structure, validate_observation, values, permission_gate, validate_uc_state
from .checkpoints import page_requirements, transaction_active, create_checkpoint
from .profile import ProfileError, _event, now

BASE='https://apply.universityofcalifornia.edu'
TERM_LABELS={'i:onefinal':'Full year (1 final grade per year)',
             'i:semester':'Semester (2 final grades per year)',
             'i:Trimester':'Trimester (3 final grades per year)',
             'i:Quarter':'Quarter (4 final grades per year)'}
GRADING_CODES={'A','B','3','4','5','6','7','8','9','D','E','F','13','14','15','16','27','18',
               '19','20','26','21','28','I','29','30','23','H','C','G'}


def school_form_blockers(page):
    """Validate only the observed existing graduating-school shape, not new schools."""
    validate_observation(page)
    url=urlsplit(page['url']);query=parse_qs(url.query)
    fields={f['key']:f for f in page['fields']}
    plain={'i:startMonth','i:startYear','i:endMonth','i:endYear','i:hsDegreeSelect',
           'i:gradMonth','i:gradYear','i:langOfInstruction'}
    special={'i:specialCurr-carrpath','i:specialCurr-ib','i:specialCurr-magnet','i:specialCurr-other'}
    grades={f'i:attend{part}{i}' for i in range(4) for part in ('grade','syear','summer')}
    grading={f'i:grading_sys_{code}' for code in GRADING_CODES}
    radio='n:currentAcadHistFrHighSchool.graduationFlag'
    expected=plain|special|grades|grading|set(TERM_LABELS)|{radio}
    if (url.scheme+'://'+url.netloc!=BASE or url.path!='/my-application/acadHistFrInfo'
            or query.get('action')!=['edit'] or set(query)!={'action','schId'}
            or len(query['schId'])!=1 or not re.fullmatch(r'\d+',query['schId'][0])
            or page.get('title')!='High school information - Academic history - UC application'
            or page.get('frames_present') or page.get('collections') or page.get('scope')
            or set(fields)!=expected):
        return [{'reason':'observed_existing_uc_school_shape_required'}]
    blockers=[]
    from .adapters.uc import MANUAL
    for key,f in fields.items():
        checkbox=key in special|grading|set(TERM_LABELS) or key in {f'i:attendsummer{i}' for i in range(4)}
        control='radio' if key==radio else 'checkbox' if checkbox else 'select'
        if f['control']!=control or f.get('readonly') or not f.get('selector') or f.get('invalid'):
            blockers.append({'reason':'known_valid_uc_school_controls_required','field_key':key})
        if f['control']=='checkbox' and type(f['value']) is not bool:
            blockers.append({'reason':'explicit_boolean_control_required','field_key':key})
        narrative=f['label']+' '+f.get('group','')
        degree_group='Degree, diploma, or certification received or to be received. *'
        if key=='i:hsDegreeSelect' and f['label']=='Degree select' and f.get('group')==degree_group:
            narrative=f['label']
        if MANUAL.search(narrative):
            blockers.append({'reason':'school_narrative_or_attestation_excluded','field_key':key})
        if key!=radio and (f.get('selector')!='[id="'+key[2:]+'"]' or f.get('selector_count',1)!=1 or f.get('selector_index',0)!=0):
            blockers.append({'reason':'unique_uc_school_controls_required','field_key':key})
        if key in TERM_LABELS and (f['label']!=TERM_LABELS[key] or f.get('disabled')):
            blockers.append({'reason':'observed_uc_term_choices_required','field_key':key})
        if f['control'] in {'select','radio'} and f['value'] and not any(o['value']==f['value'] and not o.get('disabled') for o in f['options']):
            blockers.append({'reason':'valid_existing_uc_school_choice_required','field_key':key})
    # Inactive add-another-grade slots inherit required from their fieldset.
    # A half-filled pair is an actual missing required answer, never a new year.
    active=0
    for i in range(4):
        grade=fields[f'i:attendgrade{i}'];year=fields[f'i:attendsyear{i}'];summer=fields[f'i:attendsummer{i}']
        if bool(grade['value'])!=bool(year['value']) or (not grade['value'] and summer['value']):
            blockers.append({'reason':'complete_existing_attendance_pair_required','row':i})
        if grade['value'] and year['value']:
            active+=1
            if grade.get('disabled') or year.get('disabled'):
                blockers.append({'reason':'editable_existing_attendance_pair_required','row':i})
    if not active:blockers.append({'reason':'existing_attendance_required'})
    for key in plain:
        if not fields[key]['value'] or fields[key].get('disabled'):
            blockers.append({'reason':'complete_existing_school_facts_required','field_key':key})
    yes=next((o['value'] for o in fields[radio]['options'] if o['label']=='Yes' and not o.get('disabled')),None)
    if fields[radio]['value']!=yes or yes is None:
        blockers.append({'reason':'observed_graduating_school_variant_required'})
    if not any(fields[key]['value'] for key in grading):blockers.append({'reason':'existing_grading_scale_required'})
    if any(fields[key]['value'] for key in special) or any(fields[key]['value'] for key in grading if key!='i:grading_sys_4'):
        blockers.append({'reason':'observed_bc_school_variant_required'})
    if not fields['i:semester']['value'] or fields['i:Trimester']['value'] or fields['i:Quarter']['value']:
        blockers.append({'reason':'observed_semester_school_variant_required'})
    actions=[a for a in page['actions'] if a['key']=='i:save-btn' and a['label']=='Save & continue' and not a['disabled']]
    if len(actions)!=1:blockers.append({'reason':'unique_school_draft_save_required'})
    return blockers


def preview_term_availability(profile,target_id,page):
    if any(transaction_active(c) for c in profile['checkpoints'].values()):
        raise ProfileError('pending_transaction_requires_recovery')
    target=profile['targets'].get(target_id,{})
    if target.get('system')!='uc':raise ProfileError('student_selected_uc_target_required')
    blockers=school_form_blockers(page)
    refs=['education.uc_ap_reporting_term','education.uc_other_settings_retained']
    gate=page_requirements(profile,fact_ids=refs)
    if not gate['data_ready']:blockers.append({'reason':'page_data_gate_failed','details':gate})
    if profile['facts'].get(refs[0],{}).get('value')!='Full year':
        blockers.append({'reason':'explicit_uc_ap_yearly_choice_required'})
    if profile['facts'].get(refs[1],{}).get('value') is not True:
        blockers.append({'reason':'explicit_uc_other_setting_retention_required'})
    original=values(page)
    writes=[] if original.get('i:onefinal') is True else [{'field_key':'i:onefinal','value':True,'fact_ref':refs[0]}]
    return {'schema':'uc-term-availability-preview/1','data_ready':not blockers,
        'automatic_execution_available':False,'page_url':page['url'],
        'observation_sha256':digest(page),'structure_sha256':digest(structure(page)),
        'expected_values_sha256':digest({**original,'i:onefinal':True}),
        'proposed_writes':writes,'blockers':blockers,
        'next_gate':'persist_and_verify_whole_school_course_and_status_recovery_before_input'}


def annotated_school(bundle):
    return {**bundle['school'],'uc_school_terms':{'schema':'uc-school-terms/1','identity_sha256':bundle['school_identity_sha256']},
            'state_metadata':bundle['state_metadata']}


def validate_term_bundle(bundle,*,original=False):
    """Four actual editor snapshots are temporary recovery data in one profile."""
    if bundle.get('schema')!='uc-school-term-bundle/1':raise ProfileError('school_term_bundle_schema_required')
    if not re.fullmatch(r'[a-f0-9]{64}',bundle.get('school_identity_sha256','')):
        raise ProfileError('observed_school_identity_required')
    school=bundle['school']
    if school_form_blockers(school):raise ProfileError('observed_school_term_form_required')
    validate_uc_state(bundle['state_metadata'],annotated_school(bundle))
    auxiliary=bundle['auxiliary']
    if (auxiliary.get('schema')!='uc-empty-comments/1' or auxiliary.get('page_url')!=BASE+'/my-application/acadHistAddInformation'
            or auxiliary.get('values_sha256')!=digest({'i:additional_comments':''})
            or not re.fullmatch(r'[a-f0-9]{64}',auxiliary.get('structure_sha256',''))):
        raise ProfileError('empty_uc_comments_recovery_baseline_required')
    courses=bundle['courses']
    if not isinstance(courses,list) or len(courses)!=4:raise ProfileError('all_four_course_baselines_required')
    seen=[]
    for entry in courses:
        page=entry['page'];summary=entry['summary'];context=summary['context']
        validate_observation(page)
        match=re.fullmatch(re.escape(BASE)+r'/my-application/acadHistFrHighSchoolClasses/editClasses/(09|10|11|12)/\d+',page['url'])
        if (not match or context['grade']!=match[1] or context['summary_url']!=BASE+'/my-application/acadHistFrGrades/'+match[1]
                or page.get('frames_present') or page.get('collections') or page.get('scope') or not page['fields']
                or page['title']!='Enter HS classes - Academic history - UC application'
                or not re.fullmatch(r'[a-f0-9]{64}',summary.get('rows_sha256',''))
                or not any(a['key']=='i:cancel-btn' and a['label']=='Cancel' and not a['disabled'] for a in page['actions'])):
            raise ProfileError('observed_course_recovery_baseline_required')
        if original:
            validate_observation({**page,'uc_course_editor':context,'uc_course_parent':summary['parent'],
                                  'uc_academic_auxiliary':auxiliary})
        seen.append(match[1])
    if seen!=['09','10','11','12']:raise ProfileError('all_four_course_baselines_required')


def prepare_term_test(profile,target_id,bundle,context):
    validate_term_bundle(bundle,original=True)
    preview=preview_term_availability(profile,target_id,bundle['school'])
    if not preview['data_ready'] or len(preview['proposed_writes'])!=1:
        raise ProfileError('ready_new_school_term_proposal_required')
    page=annotated_school(bundle)
    permission_gate(context,page,BASE)
    if (context.get('real_account_test') is not True or context.get('restoration_strategy',{}).get('kind')!='restore_uc_school_terms'
            or context['restoration_strategy'].get('baseline_related_sha256')!=digest(bundle['courses'])):
        raise ProfileError('school_and_course_recovery_evidence_required')
    checkpoint=create_checkpoint(profile,target_id,page['url'],fact_ids=['education.uc_ap_reporting_term','education.uc_other_settings_retained'])
    original=values(page)
    plan={'schema':'uc-school-term-plan/1','ready':True,'system':'uc','allowed_origin':BASE,
        'checkpoint_id':checkpoint,'page_url':page['url'],'bundle_sha256':digest(bundle),
        'structure_sha256':digest(structure(page)),'expected_values_sha256':preview['expected_values_sha256'],
        'school_identity_sha256':bundle['school_identity_sha256'],
        'native_shape_sha256':digest({**structure(bundle['school']),'url':None}),
        'original_values_sha256':digest(original),
        'writes':preview['proposed_writes'],'save_action':next(a for a in page['actions'] if a['key']=='i:save-btn'),
        'auxiliary':copy.deepcopy(bundle['auxiliary'])}
    cp=profile['checkpoints'][checkpoint]
    cp.update(kind='uc_school_terms',state='prepared',journal=copy.deepcopy(original),
        original_values_sha256=digest(original),expected_values_sha256=plan['expected_values_sha256'],
        observed_structure=structure(page),context=copy.deepcopy(context),prepared_plan=copy.deepcopy(plan),
        related_journal=copy.deepcopy(bundle['courses']),original_state_metadata=copy.deepcopy(bundle['state_metadata']),
        prepared_at=now())
    _event(profile,'uc_school_term_recovery_prepared',[checkpoint])
    return plan


def verify_term_test(profile,checkpoint,bundle,*,revisited_after_save,restoration=False):
    cp=profile['checkpoints'].get(checkpoint)
    if not cp or cp.get('kind')!='uc_school_terms' or cp.get('journal') is None or cp.get('state') not in {'prepared','verified','needs_restore','saved_unverified'}:
        raise ProfileError('prepared_school_term_checkpoint_required')
    validate_term_bundle(bundle,original=restoration)
    page=annotated_school(bundle)
    expected=cp['original_values_sha256'] if restoration else cp['expected_values_sha256']
    valid=(revisited_after_save is True and page['url']==cp['page_key']
        and digest(structure(page))==digest(cp['observed_structure']) and digest(values(page))==expected
        and bundle['school_identity_sha256']==cp['prepared_plan']['school_identity_sha256']
        and bundle['state_metadata']==cp['original_state_metadata'] and bundle['auxiliary']==cp['prepared_plan']['auxiliary'])
    if restoration:
        valid=valid and digest(bundle['courses'])==digest(cp['related_journal'])
    else:
        # Enabling another available term may add selectors, but may not change
        # a single original course value or a summary's actual course rows.
        for original,current in zip(cp['related_journal'],bundle['courses']):
            current_values=values(current['page'])
            valid=valid and not any(f.get('invalid') for f in current['page']['fields'])
            valid=valid and original['page']['url']==current['page']['url']
            valid=valid and original['summary']['rows_sha256']==current['summary']['rows_sha256']
            valid=valid and all(current_values.get(key)==value for key,value in values(original['page']).items())
    cp['state']='restored' if valid and restoration else 'verified' if valid else 'needs_restore'
    if valid and restoration:
        cp['restored_related_sha256']=digest(cp.pop('related_journal'))
        cp['restored_state_sha256']=digest(cp.pop('original_state_metadata'))
        cp['journal']=None;cp.pop('prepared_plan')
    _event(profile,'uc_school_term_restored' if valid and restoration else 'uc_school_term_checked',[checkpoint])
    return {'verified':bool(valid),'restored':bool(valid and restoration),'state':cp['state']}


def recover_term_test(profile,checkpoint,bundle):
    cp=profile['checkpoints'].get(checkpoint)
    if not cp or cp.get('kind')!='uc_school_terms' or cp.get('journal') is None or cp.get('state') not in {'prepared','verified','needs_restore','saved_unverified'}:
        raise ProfileError('prepared_school_term_checkpoint_required')
    page=annotated_school(bundle)
    # Unknown related editor shapes must not prevent restoring the one known
    # school checkbox. Their original snapshots remain until final verification.
    validate_observation(page)
    if page['url']!=cp['page_key'] or digest(structure(page))!=digest(cp['observed_structure']):
        raise ProfileError('school_restoration_structure_changed_handoff_required')
    current=values(page)
    writes=[{'field_key':key,'value':value} for key,value in cp['journal'].items() if current[key]!=value]
    if any(w['field_key']!='i:onefinal' for w in writes):
        raise ProfileError('unexpected_school_field_change_recovery_preserved')
    return {'plan':copy.deepcopy(cp['prepared_plan']),'writes':writes,
        'context':{**cp['context'],'journal_persisted':True},
        'original_state_metadata':copy.deepcopy(cp['original_state_metadata']),
        'original_values_sha256':cp['original_values_sha256'],
        'related_recovery_available':True}


def recover_term_warning(profile,checkpoint):
    """Read-only restart kit; the browser must freshly verify the POST alias."""
    cp=profile['checkpoints'].get(checkpoint)
    if (not cp or cp.get('kind')!='uc_school_terms' or cp.get('journal') is None
            or cp.get('state') not in {'prepared','verified','needs_restore','saved_unverified'}):
        raise ProfileError('prepared_school_term_checkpoint_required')
    plan=cp['prepared_plan']
    if cp['journal'].get('i:onefinal') is not False or plan['writes']!=[
            {'field_key':'i:onefinal','value':True,'fact_ref':'education.uc_ap_reporting_term'}]:
        raise ProfileError('known_school_term_warning_recovery_required')
    return {'plan':copy.deepcopy(plan),'context':{**cp['context'],'journal_persisted':True},
        'post_warning_cancel':True,'requires_fresh_ui_identity_verification':True,
        'original_state_metadata':copy.deepcopy(cp['original_state_metadata']),
        'original_values_sha256':cp['original_values_sha256']}
