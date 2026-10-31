"""Pure data/source checks; these tests never open a browser."""
import copy
import pytest

from bc_application import generic_forms as generic
from bc_application.browser import digest
from bc_application.checkpoints import transaction_active
from bc_application.operations import apply_operations
from bc_application.profile import ProfileError,add_statement,add_exam,set_fact,register_exam_release_schedule,validate_exam_release_schedule
from bc_application.source_refs import metadata_value,dependencies,average_details,original_date
from test_generic_forms import scenario,field,classify,record_scenario,filled,opt_out_readback,save_receipt
from bc_application.pages import build_plan,prepare


def average_case():
    p,*_=scenario();row=next(c for c in p['academic']['courses'] if c['raw_cells']['school_percent']=='84')
    second=copy.deepcopy(row);second['record_id']+=':second';second['raw_cells']['school_percent']='85'
    p['academic']['courses'].append(second)
    source=add_statement(p,'You may calculate the full-year mean of all recorded percentages.')
    set_fact(p,'education.psr_average_policies',{row['context_id']:{'method':'arithmetic_mean_all_recorded_percentages','decimals':2,'rounding':'half_up'}},source)
    return p,row,second,'psr-average:'+row['context_id']+':percent'


def test_average_is_explicit_all_rows_percent_not_a_rewritten_school_gpa():
    p,row,second,ref=average_case();before=copy.deepcopy(p['academic'])
    assert metadata_value(p,ref)=='84.50'
    assert metadata_value(p,ref.rsplit(':',1)[0]+':scale')=='100'
    assert dependencies(ref,p)==['education.psr_average_policies'] and p['academic']==before


@pytest.mark.parametrize('change',['no_policy','document_permission','missing_mark','wrong_policy','wrong_context','out_of_range'])
def test_average_never_silently_drops_unknown_marks_or_invents_permission(change):
    p,row,second,ref=average_case()
    if change=='no_policy':del p['facts']['education.psr_average_policies']
    if change=='document_permission':p['facts']['education.psr_average_policies']['source_refs']=[p['psr_source_id']]
    if change=='missing_mark':second['raw_cells']['school_percent']=''
    if change=='wrong_policy':p['facts']['education.psr_average_policies']['value'][row['context_id']]['method']='best_core_subjects'
    if change=='wrong_context':ref='psr-average:unknown:percent'
    if change=='out_of_range':second['raw_cells']['school_percent']='101'
    with pytest.raises(ProfileError):metadata_value(p,ref)


def best_five_case():
    p,*_=scenario();template=copy.deepcopy(p['academic']['courses'][0]);rows=[]
    # Context grade/year deliberately differs from the course title suffix.
    for level,scores in [('11',[81,94,89,96,93,98]),('12',[88,90,92,95,99,97])]:
        for i,score in enumerate(scores):
            row=copy.deepcopy(template);row['record_id']=f'fictional:{level}:{i}'
            row['raw_cells'].update(course_description=f'FICTIONAL SUBJECT {i} {level}',school_percent=str(score),completion_date='17-Feb-2028')
            rows.append(row)
    p['academic']['courses']=rows
    source=add_statement(p,'For each course-title level, calculate the five highest achieved percentages.')
    set_fact(p,'education.psr_average_policies',{f'course-level-{level}':{
        'method':'arithmetic_mean_best_percentages_by_course_suffix','course_level':level,
        'count':5,'decimals':2,'rounding':'half_up'} for level in ('11','12')},source)
    return p,rows


def test_best_five_uses_course_suffix_across_contexts_and_keeps_evidence():
    p,rows=best_five_case();before=copy.deepcopy(p['academic'])
    assert metadata_value(p,'psr-average:course-level-11:percent')=='94.00'
    assert metadata_value(p,'psr-average:course-level-12:percent')=='94.60'
    assert metadata_value(p,'psr-average:course-level-12:scale')=='100'
    result=average_details(p,'course-level-11')
    assert len(result['record_ids'])==5 and len(result['eligible_record_ids'])==6
    assert rows[0]['record_id'] not in result['record_ids'] and p['academic']==before
    rows[-1]['raw_cells']['course_description']='FICTIONAL ADVANCED SUBJECT 12A'
    assert metadata_value(p,'psr-average:course-level-12:percent')=='94.60'


def test_best_five_does_not_estimate_pending_or_use_code_or_context_for_title_level():
    p,rows=best_five_case();pending=copy.deepcopy(rows[0]);pending['record_id']='pending'
    pending['raw_cells'].update(course_description='FUTURE COURSE 11',school_percent='',completion_date='')
    wrong=copy.deepcopy(rows[0]);wrong['record_id']='wrong-title';wrong['raw_cells'].update(course_description='SUBJECT 10',school_percent='100',course_code='MXX11---')
    p['academic']['courses']+=[pending,wrong]
    assert metadata_value(p,'psr-average:course-level-11:percent')=='94.00'
    pending['raw_cells']['completion_date']='17-Feb-2028'
    with pytest.raises(ProfileError):metadata_value(p,'psr-average:course-level-11:percent')


@pytest.mark.parametrize('change',['too_few','invalid_low_mark','wrong_method','wrong_level','no_authorization'])
def test_best_five_cannot_hide_bad_candidates_or_relax_authorization(change):
    p,rows=best_five_case();policy=p['facts']['education.psr_average_policies']
    if change=='too_few':p['academic']['courses']=rows[:4]
    if change=='invalid_low_mark':rows[0]['raw_cells']['school_percent']='-1'
    if change=='wrong_method':policy['value']['course-level-11']['count']=4
    if change=='wrong_level':policy['value']['course-level-11']['course_level']='12'
    if change=='no_authorization':policy['source_refs']=[p['psr_source_id']]
    with pytest.raises(ProfileError):metadata_value(p,'psr-average:course-level-11:percent')


def test_result_dates_need_explicit_policy_and_current_enrollment():
    p,row,_,_=average_case();source=add_statement(p,'Completed results use original completion dates; this listed course is in progress with a specified result date.')
    set_fact(p,'education.course_result_date_policy',{'completed':'psr_completion_date','in_progress':'2028-02-17'},source)
    prefix='psr-course:'+row['record_id']
    assert metadata_value(p,prefix+':level')=='10'
    assert metadata_value(p,prefix+':result_pending') is False
    assert metadata_value(p,prefix+':result_status')=='Achieved'
    assert metadata_value(p,prefix+':result_release_date')==metadata_value(p,prefix+':completion_date')
    row['raw_cells']['school_percent']='';row['raw_cells']['completion_date']=''
    with pytest.raises(ProfileError):metadata_value(p,prefix+':result_release_date')
    set_fact(p,'education.current_year.report',{'courses':[{'record_ids':[row['record_id']]}]},source)
    set_fact(p,'education.current_year.enrollment',[row['record_id']],source)
    assert metadata_value(p,prefix+':result_release_date')=='2028-02-17'
    assert metadata_value(p,prefix+':result_pending') is True
    assert metadata_value(p,prefix+':result_status')=='Pending'


def test_exam_metadata_reuses_one_date_fact_and_preserves_score_scale():
    p,*_=scenario();source=add_statement(p,'Two fictional AP results share the same confirmed exam month.')
    a=add_exam(p,name='AP Fictional A',system='AP',score=5,scale='1-5',source_id=source)
    b=add_exam(p,name='AP Fictional B',system='AP',score=4,scale='1-5',source_id=source)
    apply_operations(p,[{'op':'fact','field':'exams.shared.date','value':'2026-05','source':source},
        *[{'op':'exam_date_ref','exam':key,'field':'exams.shared.date','source':source} for key in (a,b)]])
    assert p['exams'][a]['date_fact_id']==p['exams'][b]['date_fact_id']=='exams.shared.date'
    assert metadata_value(p,'exam-record:'+a+':score')==5
    assert metadata_value(p,'exam-record:'+b+':date')=='2026-05'
    assert metadata_value(p,'exam-record:'+a+':scale')=='1-5'


def test_course_dialog_name_alias_requires_original_name_and_separate_sourced_level():
    p,t,pg,_,ctx=scenario();row=next(c for c in p['academic']['courses'] if c['raw_cells']['school_percent']=='84');rid=row['record_id']
    pg['generic_form']['dialog']={'name':'Course record','selector':'#course','selector_count':1}
    pg['fields']=[field('Grade','select',options=['10','11','12'],seed=991),field('Subject','select',options=['Observed alias'],seed=992),field('Achieved score','text',seed=993)]
    a=classify(pg,[('psr-course:'+rid+':level','fact'),('psr:'+rid+':description','academic_name'),('psr:'+rid+':school_percent','academic_mark')])
    a['record']={'ref':'psr-course:'+rid};a['fields'][1].update(format='observed_label',choice={'source_value':row['raw_cells']['course_description'],'label':'Observed alias','level':'10'})
    assert build_plan(p,t,pg,semantic_analysis=a)['ready']
    a['fields'][1]['choice']['source_value']='Another original course'
    assert not build_plan(p,t,pg,semantic_analysis=a)['ready']


def test_canceled_blank_editor_checkbox_drift_is_not_claimed_as_exact_restoration():
    p,t,pg,a,ctx=record_scenario();checkbox=field('Pending','checkbox',required=False,value=False,seed=994)
    pg['fields'].append(checkbox);a['fields'].append({'key':checkbox['key'],'label':checkbox['label'],'group':'','control':'checkbox','role':'skip_optional','ref':None,'purpose':None,'format':'identity','reason':'Preserve optional original state.'})
    a['observation_sha256']=digest(pg);plan=build_plan(p,t,pg,semantic_analysis=a);prepare(p,plan['checkpoint_id'],pg,ctx)
    canceled=copy.deepcopy(pg);canceled['fields'][-1]['disabled']=True
    result=generic.cancel(p,plan['checkpoint_id'],canceled,revisited_saved_draft=True)
    assert result['draft_discarded'] and not result['restored'] and not transaction_active(p['checkpoints'][plan['checkpoint_id']])
    assert p['checkpoints'][plan['checkpoint_id']]['journal'] is not None


def test_record_views_are_observed_and_create_distinct_editor_instances():
    p,t,pg,a,ctx=record_scenario();a['record_view']=pg['generic_form']['dialog']['name']
    first=build_plan(p,t,pg,semantic_analysis=a)['checkpoint_id']
    pg['generic_form']['dialog']['name']='Another public editor';a['record_view']='Another public editor';a['observation_sha256']=digest(pg)
    second=build_plan(p,t,pg,semantic_analysis=a)['checkpoint_id'];assert first!=second
    a['record_view']='Unobserved view'
    with pytest.raises(ProfileError):build_plan(p,t,pg,semantic_analysis=a)


def test_school_prediction_absence_is_a_blocker_without_repeating_the_question():
    p,t,pg,_,_=scenario();source=add_statement(p,'The school has not provided this course prediction.')
    rid=p['academic']['courses'][0]['record_id'];ref='education.course_predictions.'+rid
    set_fact(p,'education.course_prediction_availability',{rid:False},source)
    pg['fields']=[field('Predicted score','text',seed=995)];a=classify(pg,[(ref,'fact')])
    plan=build_plan(p,t,pg,semantic_analysis=a)
    assert not plan['ready'] and not plan['questions']
    assert plan['unavailable_facts'][0]['reason']=='school_prediction_not_provided'
    set_fact(p,'education.course_prediction_availability',{rid:True},add_statement(p,'The school may have a prediction now.'))
    assert build_plan(p,t,pg,semantic_analysis=a)['questions']


def test_calendar_controller_can_reveal_new_requirements_without_saving():
    p,t,pg,a,ctx=record_scenario();controller=pg['fields'][1]
    plan=generic.prepare_stage(p,t,pg,a,ctx,controller['key'])
    assert plan['generic_stage'] and plan['save_action'] is None
    assert plan['writes'][0]['field_key']==controller['key']


def nested_exam_case():
    p,t,pg,_,ctx=scenario();opt_out_readback(p);s=add_statement(p,'A fictional AP result and its explicit result-release day.')
    exam=add_exam(p,name='Fictional AP',system='AP',score=5,scale='1-5',source_id=s,date='2028-05')
    set_fact(p,'exams.shared.release_date','2028-07-17',s)
    pg['generic_form']['view']={'name':'Fictional AP results'}
    pg['fields']=[field('Result release','text',seed=996)];pg['fields'][0]['widget']={'kind':'calendar','native_readonly':True}
    a=classify(pg,[('exams.shared.release_date','date')]);a['fields'][0]['format']='date_dmy'
    descriptor={'ref':'exam-record:'+exam};a['child_records']=[descriptor]
    stage=generic.prepare_stage(p,t,pg,a,ctx,pg['fields'][0]['key']);parent=stage['checkpoint_id']
    child=copy.deepcopy(pg);child['generic_form'].pop('view');child['generic_form']['dialog']={'name':'AP score','selector':'#exam','selector_count':1}
    child['fields']=[field('Score','text',seed=997)]
    ca=classify(child,[('exam-record:'+exam+':score','fact')]);ca.update(record=descriptor,parent_checkpoint_id=parent)
    return p,t,pg,a,ctx,stage,child,ca


def test_nested_exam_save_keeps_parent_journal_and_requires_child_receipt():
    p,t,pg,a,ctx,stage,child,ca=nested_exam_case();key=stage['checkpoint_id'];original=copy.deepcopy(p['checkpoints'][key]['journal'])
    expanded=filled(pg,stage);fresh={**a,'observation_sha256':digest(expanded)}
    assert not generic.accept_stage(p,key,expanded,fresh)['ready']
    plan=build_plan(p,t,child,semantic_analysis=ca);assert plan['ready']
    prepare(p,plan['checkpoint_id'],child,ctx)
    assert generic.acknowledge_save(p,plan['checkpoint_id'],save_receipt(plan))['saved']
    assert transaction_active(p['checkpoints'][key]) and p['checkpoints'][key]['journal']==original
    assert generic.accept_stage(p,key,expanded,fresh)['ready']


def test_session_loss_can_discard_only_an_empty_unsaved_date_view_without_children():
    p,t,pg,a,ctx,stage,child,ca=nested_exam_case();lost=copy.deepcopy(pg)
    lost['generic_form'].pop('view');lost['generic_form']['views']=['Another qualification'];lost['fields']=[]
    key=stage['checkpoint_id'];result=generic.cancel(p,key,lost,revisited_saved_draft=True)
    assert result['draft_discarded'] and not result['restored'] and not transaction_active(p['checkpoints'][key])
    assert p['checkpoints'][key]['journal'] is not None
    p,t,pg,a,ctx,stage,child,ca=nested_exam_case();key=stage['checkpoint_id']
    p['checkpoints'][key]['journal'][next(iter(p['checkpoints'][key]['journal']))]='An existing date'
    assert not generic.cancel(p,key,lost,revisited_saved_draft=True)['restored']
    assert transaction_active(p['checkpoints'][key])


def view_case():
    p,t,pg,a,ctx=scenario();opt_out_readback(p)
    pg['generic_form'].update(view={'name':'View one'},views=['View one','View two'])
    a['observation_sha256']=digest(pg)
    plan=build_plan(p,t,pg,semantic_analysis=a);prepare(p,plan['checkpoint_id'],pg,ctx)
    previous=filled(pg,plan);following=copy.deepcopy(pg);following['generic_form']['view']={'name':'View two'}
    following['fields']=[field('Given name in the second view','text',seed=999)]
    proposal=classify(following,[('personal.legal_given_name','name')]);proposal['save_mode']='stay'
    return p,t,previous,following,proposal,ctx,plan


def test_same_form_view_handover_keeps_one_active_journal_and_all_frozen_sources():
    p,t,previous,following,a,ctx,old=view_case();key=old['checkpoint_id'];original=copy.deepcopy(p['checkpoints'][key]['journal'])
    next_plan=generic.switch_view(p,key,previous,following,a)
    assert next_plan['ready'] and next_plan['checkpoint_id']==key
    assert p['checkpoints'][key]['generic_view_history'][0]['journal']==original
    assert sum(transaction_active(c) for c in p['checkpoints'].values())==1
    assert generic.acknowledge_save(p,key,save_receipt(next_plan))['saved']
    assert p['checkpoints'][key]['generic_view_history']


@pytest.mark.parametrize('change',['other_form','unknown_view','changed_old_value','changed_source','wrong_url','no_opt_out'])
def test_view_handover_never_discards_unobserved_values_or_switches_forms(change):
    p,t,previous,following,a,ctx,old=view_case()
    if change=='other_form':following['generic_form']['scope']['selector']='#different'
    if change=='unknown_view':following['generic_form']['view']['name']='Unknown'
    if change=='changed_old_value':previous['fields'][0]['value']='Changed without a prepared source'
    if change=='changed_source':p['facts']['personal.legal_given_name']['value']='Different'
    if change=='wrong_url':following['url']+='/different'
    if change=='no_opt_out':p['facts'][generic.READBACK_POLICY]['value']=True
    a['observation_sha256']=digest(following)
    with pytest.raises(ProfileError):generic.switch_view(p,old['checkpoint_id'],previous,following,a)


def test_ielts_component_identity_is_readonly_and_cannot_be_renamed():
    p,t,pg,_,ctx=scenario();s=add_statement(p,'A fictional IELTS result with explicit components.')
    exam=add_exam(p,name='IELTS Academic',system='IELTS',score=7,scale='IELTS_0_to_9',source_id=s,date='2028-02-17')
    component=p['exams'][exam]['score_fact_id'].rsplit('.',1)[0]+'.listening'
    set_fact(p,component,8,s,scale='IELTS_0_to_9')
    pg['generic_form']['dialog']={'name':'Score editor','selector':'#score','selector_count':1}
    pg['fields']=[field('Subject','text',value='Listening',seed=1001),field('Achieved score','text',seed=1002)]
    pg['fields'][0]['disabled']=True
    a=classify(pg,[('exam-record:'+exam+':listening_name','fact'),(component,'fact')]);a['record']={'ref':'exam-record:'+exam,'component':component}
    assert build_plan(p,t,pg,semantic_analysis=a)['ready']
    pg['fields'][0]['value']='Reading';a['observation_sha256']=digest(pg)
    assert not build_plan(p,t,pg,semantic_analysis=a)['ready']


def test_exam_grade_requires_original_context_and_same_explicit_exam_month():
    p,*_=scenario();row=next(c for c in p['academic']['courses'] if c['raw_cells']['school_percent']=='84')
    month=original_date(row['raw_cells']['completion_date'])[:7];s=add_statement(p,'A fictional AP exam taken in this explicitly supplied month.')
    exam=add_exam(p,name='Fictional AP',system='AP',score=5,scale='1-5',source_id=s,date=month,related_course_ids=[row['record_id']])
    context=next(c for c in p['academic']['contexts'] if c['context_id']==row['context_id'])
    assert metadata_value(p,'exam-record:'+exam+':school_grade')==str(int(context['student_grade_raw'].split()[-1]))
    p['facts'][p['exams'][exam]['date_fact_id']]['value']='2030-02'
    with pytest.raises(ProfileError):metadata_value(p,'exam-record:'+exam+':school_grade')


def test_average_display_can_add_zeroes_without_rounding_or_converting_marks():
    assert generic.display_source_value({'format':'decimal_fixed_2'},'psr-average:course-level-11:scale','100')=='100.00'
    with pytest.raises(ProfileError):generic.display_source_value({'format':'decimal_fixed_2'},'psr-average:course-level-11:percent','91.125')


def official_release_case():
    p,*_=scenario();student=add_statement(p,'Use the official exam board public schedule for the AP release date.')
    exam=add_exam(p,name='AP Calculus BC',system='AP',score=5,scale='1-5',source_id=student,date='2028-05')
    args=dict(system='AP',year=2028,release_date='2028-07-17',url='https://apstudents.collegeboard.org/view-scores',
              title='Fictional public observation for unit tests',excerpt='2028 AP Exam scores will be available starting July 17.',observation_method='official_search_excerpt')
    source=register_exam_release_schedule(p,**args)
    set_fact(p,'exams.ap_result_release_policy',{'rule':'exam_board_public_schedule','exam_ids':[exam],'schedule_source_id':source},student)
    return p,exam,source,args


def test_exam_release_uses_observed_board_schedule_and_never_psr_course_date():
    p,exam,source,args=official_release_case();raw=copy.deepcopy(p['academic'])
    assert metadata_value(p,'exam-record:'+exam+':result_release_date')=='2028-07-17'
    assert p['academic']==raw
    assert p['sources'][source]['observation_method']=='official_search_excerpt'
    assert register_exam_release_schedule(p,**args)==source
    # A student's rule may authorize use of a schedule; it is not score-report evidence.
    assert p['sources'][source]['kind']=='public_exam_schedule'
    p['facts']['exams.ap_result_release_policy']['value']['rule']='linked_psr_completion_dates'
    with pytest.raises(ProfileError,match='release_rule'):metadata_value(p,'exam-record:'+exam+':result_release_date')


@pytest.mark.parametrize('change',['foreign_host','lookalike_host','http','credentials','query','wrong_year','invalid_day','missing_year','wrong_day','missing_score_text','unobserved','long_excerpt'])
def test_public_schedule_requires_bounded_official_evidence(change):
    p,*_=scenario();_,_,_,args=official_release_case()
    if change=='foreign_host':args['url']='https://example.org/view-scores'
    if change=='lookalike_host':args['url']='https://apstudents.collegeboard.org.example.org/view-scores'
    if change=='http':args['url']=args['url'].replace('https:','http:')
    if change=='credentials':args['url']=args['url'].replace('https://','https://someone:secret@')
    if change=='query':args['url']+='?student=private'
    if change=='wrong_year':args['year']=2029
    if change=='invalid_day':args['release_date']='2028-02-30'
    if change=='missing_year':args['excerpt']='AP Exam scores will be available starting July 17.'
    if change=='wrong_day':args['excerpt']='2028 AP Exam scores will be available starting July 18.'
    if change=='missing_score_text':args['excerpt']='2028 course completion is July 17.'
    if change=='unobserved':args['observation_method']='guessed'
    if change=='long_excerpt':args['excerpt']+=' extra'*30
    before=copy.deepcopy(p)
    with pytest.raises(ProfileError):register_exam_release_schedule(p,**args)
    assert p==before


def test_public_schedule_cannot_change_after_registration_or_cross_exam_years():
    p,exam,source,_=official_release_case()
    p['sources'][source]['release_date']='2028-07-18'
    with pytest.raises(ProfileError):validate_exam_release_schedule(source,p['sources'][source])
    p,exam,source,_=official_release_case();p['facts'][p['exams'][exam]['date_fact_id']]['value']='2027-05'
    with pytest.raises(ProfileError,match='administration'):metadata_value(p,'exam-record:'+exam+':result_release_date')


def test_ab_subscore_is_explicit_parent_component_without_another_exam_or_course():
    p,exam,_,_=official_release_case();count=len(p['exams']);courses=copy.deepcopy(p['academic'])
    ref='exam-record:'+exam;component=p['exams'][exam]['score_fact_id'].rsplit('.',1)[0]+'.ab_subscore'
    with pytest.raises(ProfileError):metadata_value(p,ref+':ab_subscore')
    source=add_statement(p,'The fictional AB subscore is four, independently of a five on BC.')
    set_fact(p,component,4,source,scale='1-5')
    assert metadata_value(p,ref+':ab_subscore')==4
    assert metadata_value(p,ref+':ab_subscore_name')=='Calculus AB SUBSCORE'
    assert metadata_value(p,ref+':score')==5
    generic.validate_exam_component(p,{'ref':ref,'component':component})
    assert len(p['exams'])==count and p['academic']==courses
    p['exams'][exam]['name']='AP Calculus AB'
    with pytest.raises(ProfileError):metadata_value(p,ref+':ab_subscore')
    with pytest.raises(ProfileError):generic.validate_exam_component(p,{'ref':ref,'component':component})


def test_ab_subscore_editor_has_a_distinct_parent_component_identity():
    p,exam,_,_=official_release_case();_,_,pg,_,_=scenario();target=next(iter(p['targets']))
    prefix=p['exams'][exam]['score_fact_id'].rsplit('.',1)[0];component=prefix+'.ab_subscore'
    set_fact(p,component,4,add_statement(p,'Explicit fictional AB subscore: four.'),scale='1-5')
    pg['generic_form']['dialog']={'name':'AP score editor','selector':'#ap-editor','selector_count':1}
    pg['fields']=[field('Subject','select',options=['Calculus BC','Calculus AB SUBSCORE'],seed=1005),field('Achieved score','text',seed=1006)]
    a=classify(pg,[('exam-record:'+exam+':ab_subscore_name','fact'),(component,'fact')]);a['record']={'ref':'exam-record:'+exam,'component':component}
    plan=build_plan(p,target,pg,semantic_analysis=a)
    assert plan['ready'] and any(w['value']=='4' for w in plan['writes'])
    p['facts'][component]['value']=5.5
    with pytest.raises(ProfileError):build_plan(p,target,pg,semantic_analysis=a)


def test_course_level_does_not_replace_exam_student_grade():
    p,*_=scenario();row=next(c for c in p['academic']['courses'] if c['raw_cells']['school_percent']=='84')
    context=next(c for c in p['academic']['contexts'] if c['context_id']==row['context_id'])
    row['raw_cells'].update(course_code='ACAL-2A---',course_description='AP CALCULUS BC 12A')
    context['student_grade_raw']='Grade 11';original=copy.deepcopy(p['academic'])
    exam=add_exam(p,name='AP Calculus BC',system='AP',score=5,scale='1-5',source_id=add_statement(p,'Explicit fictional AP administration.'),
                  date=original_date(row['raw_cells']['completion_date'])[:7],related_course_ids=[row['record_id']])
    assert metadata_value(p,'psr-course:'+row['record_id']+':level')=='12'
    assert metadata_value(p,'exam-record:'+exam+':school_grade')=='11'
    assert p['academic']==original


def test_same_visible_average_is_reentered_with_native_numeric_input_events():
    p,row,_,ref=average_case();_,_,pg,_,_=scenario();target=next(iter(p['targets']))
    pg['fields']=[field('Calculated average','text',value='84.50',seed=1004)]
    a=classify(pg,[(ref,'fact')]);a['fields'][0]['format']='decimal_fixed_2'
    plan=build_plan(p,target,pg,semantic_analysis=a)
    assert plan['ready'] and plan['writes']==[{'field_key':pg['fields'][0]['key'],'value':'84.50','fact_ref':ref,'numeric_input':True}]


@pytest.mark.parametrize('change',['missing_parent','wrong_record','changed_source','wrong_url','missing_dialog','undeclared_child'])
def test_nested_exam_cannot_bypass_active_parent_or_source_scope(change):
    p,t,pg,a,ctx,stage,child,ca=nested_exam_case()
    if change=='missing_parent':ca.pop('parent_checkpoint_id')
    if change=='wrong_record':ca['record']={'ref':'exam-record:exam:unknown'}
    if change=='changed_source':p['facts']['exams.shared.release_date']['value']='2028-07-18'
    if change=='wrong_url':child['url']+='/other'
    if change=='missing_dialog':child['generic_form'].pop('dialog')
    if change=='undeclared_child':p['checkpoints'][stage['checkpoint_id']]['semantic_analysis']['child_records']=[]
    ca['observation_sha256']=digest(child)
    with pytest.raises(ProfileError):build_plan(p,t,child,semantic_analysis=ca)
