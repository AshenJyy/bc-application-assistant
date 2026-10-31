"""Source-reference courses for the current/most recent academic year; no marks.

Grouping is an explicit student choice. It never changes, averages or replaces
the original PSR course/credit/grade records.
"""
import re

from .browser import digest
from .checkpoints import page_requirements
from .pages import resolve
from .profile import ProfileError
from .schools import fact_ref


def compile_report(profile,report_ref):
    fact_ref(report_ref);required=[report_ref];columns={};blockers=[]
    report=profile['facts'].get(report_ref,{}).get('value')
    if report is None:return {'ready':False,'required_fact_ids':required,'source_gate':page_requirements(profile,fact_ids=required),
        'blockers':[],'courses':[]}
    if (not isinstance(report,dict) or set(report)!={'schema','enrollment_ref','scheduling_ref','courses'}
            or report['schema']!='current-study-report/1' or not isinstance(report['courses'],list) or not 1<=len(report['courses'])<=25):
        raise ProfileError('explicit_current_study_report_required')
    def fact(ref):
        fact_ref(ref);required.append(ref)
        try:return resolve(profile,ref)[0]
        except ProfileError:return None
    enrollment=fact(report['enrollment_ref']);schedule=fact(report['scheduling_ref'])
    if schedule is not None and schedule not in {'Semester','Trimester','Quarter','Yearly'}:
        blockers.append({'reason':'explicit_current_school_scheduling_system_required'})
    records={c['record_id']:c for c in profile['academic']['courses']};contexts={c['context_id']:c for c in profile['academic']['contexts']}
    rows=[];seen=set();keys=set();years=set()
    for course in report['courses']:
        if (not isinstance(course,dict) or set(course)!={'key','record_ids','subject_ref','level_ref','terms_ref','label_ref','grouping_ref'}
                or not isinstance(course['key'],str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}',course['key']) or course['key'] in keys
                or not isinstance(course['record_ids'],list) or not 1<=len(course['record_ids'])<=4):
            raise ProfileError('explicit_current_course_reference_required')
        keys.add(course['key']);ids=course['record_ids'];names=[];schools=[]
        for key in ids:
            if not isinstance(key,str) or key not in records or key in seen:raise ProfileError('unique_original_current_course_required')
            seen.add(key);columns[key]=['description'];context=contexts.get(records[key]['context_id'])
            if not context or not context.get('school_year_raw'):raise ProfileError('original_current_course_context_required')
            years.add(context['school_year_raw']);schools.append(context['school_id'])
            name=resolve(profile,f'psr:{key}:description')[0]
            if not isinstance(name,str) or not name.strip():raise ProfileError('original_current_course_name_required')
            names.append(re.sub(r'\s+',' ',re.sub(r'-\r?\n\s*','-',name)).strip())
        if len(ids)==1:
            if course['label_ref'] is not None or course['grouping_ref'] is not None:raise ProfileError('single_current_course_uses_original_name')
            label=names[0]
        else:
            label=fact(course['label_ref']);group=fact(course['grouping_ref'])
            if group is not None and group!=ids:blockers.append({'reason':'explicit_current_course_phase_group_required','course_key':course['key']})
            for ref in (course['label_ref'],course['grouping_ref']):
                if ref not in profile['facts']:continue
                source=profile['facts'][ref]
                if not any(profile['sources'][s]['kind']=='student_statement' and set(ids)<=set(profile['sources'][s].get('scope',[])) for s in source['source_refs']):
                    blockers.append({'reason':'record_scoped_student_grouping_required','course_key':course['key'],'fact_ref':ref})
            if label is not None and (not isinstance(label,str) or not label.strip()):blockers.append({'reason':'explicit_grouped_course_label_required'})
        subject=fact(course['subject_ref']);level=fact(course['level_ref']);terms=fact(course['terms_ref'])
        for name,value in (('subject',subject),('level',level)):
            if value is not None and (not isinstance(value,str) or not value.strip()):blockers.append({'reason':'explicit_current_course_'+name+'_required','course_key':course['key']})
        if terms is not None and (not isinstance(terms,list) or not 1<=len(terms)<=4 or any(not isinstance(t,str) or not t.strip() for t in terms)
                or len(set(terms))!=len(terms)):
            blockers.append({'reason':'explicit_current_course_terms_required','course_key':course['key']})
        rows.append({'key':course['key'],'record_ids':list(ids),'original_names':names,'school_ids':schools,'name':label,
            'subject':subject,'level':level,'terms':terms})
    if len(years)!=1:raise ProfileError('current_courses_span_original_school_years')
    if enrollment is not None and (not isinstance(enrollment,list) or any(not isinstance(i,str) for i in enrollment)
            or len(set(enrollment))!=len(enrollment) or set(enrollment)!=seen):
        blockers.append({'reason':'explicit_complete_current_course_enrollment_required'})
    selected=list(columns);required=list(dict.fromkeys(required));gate=page_requirements(profile,fact_ids=required,course_ids=selected,record_columns=columns)
    return {'ready':gate['data_ready'] and not blockers,'scheduling_system':schedule,'courses':rows,'source_record_count':len(seen),
        'school_year_raw':next(iter(years)),'required_fact_ids':required,'required_course_ids':selected,'required_record_columns':columns,
        'source_gate':gate,'blockers':blockers,'source_fingerprint':digest({'academic_sha256':profile['academic_sha256'],
            'facts':{ref:profile['facts'].get(ref) for ref in required}})}
