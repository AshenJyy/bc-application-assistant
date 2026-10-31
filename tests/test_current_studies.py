"""Current studies are explicit, source-backed names/metadata and phase grouping."""
import copy
from pathlib import Path

import pytest

from bc_application import current_studies
from bc_application.profile import ProfileError,create_profile,add_statement,set_fact

REF='education.current_year.report'


def scenario():
    p=create_profile(Path(__file__).parent/'fixtures/synthetic_academic_psr.pdf');ids=[c['record_id'] for c in p['academic']['courses'][:3]]
    source=add_statement(p,'Fictional student explicitly supplies the current-year list, grouping, subjects, levels and terms.',scope=ids)
    report={'schema':'current-study-report/1','enrollment_ref':'education.current_year.enrollment','scheduling_ref':'education.current_year.scheduling',
        'courses':[]}
    set_fact(p,report['enrollment_ref'],ids,source);set_fact(p,report['scheduling_ref'],'Semester',source)
    for n,group in enumerate(([ids[0]],[ids[1],ids[2]]),1):
        base=f'education.current_year.course_{n}'
        for key,value in {'subject':'Other/Elective','level':'Regular/Standard','terms':['First Semester']}.items():set_fact(p,base+'.'+key,value,source)
        row={'key':'course_'+str(n),'record_ids':group,'subject_ref':base+'.subject','level_ref':base+'.level','terms_ref':base+'.terms',
            'label_ref':base+'.label' if len(group)>1 else None,'grouping_ref':base+'.group' if len(group)>1 else None}
        if len(group)>1:set_fact(p,row['label_ref'],'Explicit fictional grouped course',source);set_fact(p,row['grouping_ref'],group,source)
        report['courses'].append(row)
    set_fact(p,REF,report,source);return p,p['facts'][REF]['value']


def test_current_names_and_student_grouping_preserve_every_original_record_and_mark():
    p,report=scenario();original=copy.deepcopy(p);result=current_studies.compile_report(p,REF)
    assert result['ready'] and len(result['courses'])==2 and result['source_record_count']==3
    assert result['courses'][0]['name']==p['academic']['courses'][0]['raw_cells']['course_description']
    assert result['courses'][1]['name']=='Explicit fictional grouped course' and len(result['courses'][1]['original_names'])==2
    assert all(cols==['description'] for cols in result['required_record_columns'].values()) and p==original


@pytest.mark.parametrize('change',['enrollment','terms','subject','label','group','scope','duplicate','year','single_label'])
def test_missing_or_conflicting_current_course_information_never_gets_inferred(change):
    p,report=scenario();row=report['courses'][1]
    if change=='enrollment':del p['facts'][report['enrollment_ref']]
    if change=='terms':p['facts'][row['terms_ref']]['value']=[]
    if change=='subject':del p['facts'][row['subject_ref']]
    if change=='label':del p['facts'][row['label_ref']]
    if change=='group':p['facts'][row['grouping_ref']]['value']=row['record_ids'][:1]
    if change=='scope':p['facts'][row['grouping_ref']]['source_refs']=[add_statement(p,'An unscoped fictional claim.')]
    if change=='duplicate':row['record_ids'][0]=report['courses'][0]['record_ids'][0]
    if change=='year':row['record_ids'][0]=p['academic']['courses'][-1]['record_id']
    if change=='single_label':report['courses'][0]['label_ref']=row['label_ref']
    before=copy.deepcopy(p)
    try:assert not current_studies.compile_report(p,REF)['ready']
    except ProfileError:pass
    assert p==before
