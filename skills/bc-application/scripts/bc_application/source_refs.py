"""Read-only original PSR metadata and bounded paths within canonical facts."""
import re
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .profile import ProfileError


def is_metadata(ref):
    return isinstance(ref,str) and ref.startswith(('psr-school:','psr-context:','psr-course:','psr-average:','exam-record:','school-directory:'))


def dependencies(ref,profile=None):
    if ref.startswith('exam-record:') and profile is not None:
        key=ref[len('exam-record:'):]
        if key not in profile['exams']:key=key.rsplit(':',1)[0]
        exam=profile['exams'].get(key,{})
        component=ref.rsplit(':',1)[-1].removesuffix('_name')
        component_refs=[exam['score_fact_id'].rsplit('.',1)[0]+'.'+component] if ref.endswith('_name') and component in {'score','listening','reading','writing','speaking'} and exam.get('system')=='IELTS' else []
        if component=='ab_subscore' and exam.get('system')=='AP':
            component_refs=[exam['score_fact_id'].rsplit('.',1)[0]+'.ab_subscore']
        return [v for k in ('score_fact_id','date_fact_id') if (v:=exam.get(k))]+component_refs+(['exams.ap_result_release_policy'] if ref.endswith(':result_release_date') else [])
    if ref.startswith('psr-average:'):return ['education.psr_average_policies']
    if ref.startswith('psr-course:') and ref.endswith((':result_release_date',':result_pending',':result_status')):
        refs=['education.course_result_date_policy']
        if profile is not None:
            key=ref[len('psr-course:'):].rsplit(':',1)[0]
            course=next((c for c in profile['academic']['courses'] if c['record_id']==key),None)
            if course and not course['raw_cells']['completion_date']:refs+=['education.current_year.report','education.current_year.enrollment']
        return refs
    return []


def student_policy(profile,key):
    from .checkpoints import page_requirements
    fact=profile['facts'].get(key,{})
    if (not fact.get('source_refs') or any(profile['sources'].get(s,{}).get('kind')!='student_statement' for s in fact['source_refs'])
            or not page_requirements(profile,fact_ids=[key])['data_ready']):raise ProfileError('explicit_academic_calculation_or_date_policy_required')
    return fact['value']


def original_date(raw):
    if not isinstance(raw,str):raise ProfileError('complete_original_psr_date_required')
    months=('Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec')
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',raw):return date.fromisoformat(raw).isoformat()
        match=re.fullmatch(r'(\d{1,2})-([A-Za-z]{3})-(\d{4})',raw)
        if not match:raise ValueError()
        return date(int(match[3]),next(i for i,m in enumerate(months,1) if m.casefold()==match[2].casefold()),int(match[1])).isoformat()
    except (ValueError,StopIteration) as exc:raise ProfileError('complete_original_psr_date_required') from exc


def average_details(profile,selector):
    """Derive a student-authorized mean and its original record IDs; store no copy."""
    policies=student_policy(profile,'education.psr_average_policies')
    policy=policies.get(selector) if isinstance(policies,dict) else None
    all_rows={'method':'arithmetic_mean_all_recorded_percentages','decimals':2,'rounding':'half_up'}
    level=selector.removeprefix('course-level-') if selector.startswith('course-level-') else None
    best={'method':'arithmetic_mean_best_percentages_by_course_suffix','course_level':level,
          'count':5,'decimals':2,'rounding':'half_up'}
    if level in {'11','12'} and policy==best:
        # A title suffix is a course level, independently of its PSR academic year.
        rows=[c for c in profile['academic']['courses'] if re.search(r'\b'+level+r'[A-Z]?$',c['raw_cells']['course_description'])]
        # Blank, undated current courses have no achieved result to rank.
        rows=[c for c in rows if c['raw_cells']['school_percent'] or c['raw_cells']['completion_date']]
        count=5
    elif policy==all_rows:
        rows=[c for c in profile['academic']['courses'] if c['context_id']==selector]
        count=None
    else:raise ProfileError('explicit_original_percentage_average_policy_required')
    if not rows:raise ProfileError('original_psr_average_rows_required')
    from .checkpoints import page_requirements
    if not page_requirements(profile,fact_ids=[],course_ids=[c['record_id'] for c in rows],
            record_columns={c['record_id']:['school_percent'] for c in rows})['data_ready']:
        raise ProfileError('average_original_marks_require_review')
    marks=[]
    for c in rows:
        raw=c['raw_cells']['school_percent']
        try:
            if not isinstance(raw,str) or not re.fullmatch(r'\d+(?:\.\d+)?',raw):raise ValueError()
            mark=Decimal(raw)
            if not 0<=mark<=100:raise ValueError()
        except (ValueError,InvalidOperation) as exc:raise ProfileError('average_requires_every_original_percentage') from exc
        marks.append((mark,c['record_id']))
    if count is not None and len(marks)<count:raise ProfileError('average_requires_five_achieved_results')
    selected=sorted(marks,key=lambda m:(-m[0],m[1]))[:count] if count else marks
    return {'percent':str((sum(m for m,_ in selected)/len(selected)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)),
            'scale':'100','record_ids':[key for _,key in selected],
            'eligible_record_ids':[c['record_id'] for c in rows],'method':policy['method']}


def metadata_value(profile,ref):
    if ref.startswith('exam-record:'):
        key,column=ref[len('exam-record:'):].rsplit(':',1)
        exam=profile['exams'].get(key)
        if not exam:raise ProfileError('canonical_exam_record_required')
        from .checkpoints import page_requirements
        if not page_requirements(profile,fact_ids=dependencies(ref,profile))['data_ready']:raise ProfileError('canonical_exam_sources_require_review')
        if column in {'name','system'}:return exam[column]
        if column=='school_grade':
            # Only align an explicitly dated exam with linked PSR credit rows
            # completed in that same month and one recorded student grade.
            when=profile['facts'].get(exam.get('date_fact_id'),{}).get('value','')
            linked=[c for c in profile['academic']['courses'] if c['record_id'] in exam['related_course_ids']]
            contexts={c['context_id']:c for c in profile['academic']['contexts']}
            if not linked or not re.fullmatch(r'\d{4}-\d{2}(?:-\d{2})?',when) or any(original_date(c['raw_cells']['completion_date'])[:7]!=when[:7] for c in linked):
                raise ProfileError('documented_exam_month_grade_alignment_required')
            grades={contexts[c['context_id']]['student_grade_raw'] for c in linked}
            match=re.fullmatch(r'(?:Grade\s+)?(0?[1-9]|1[0-3])',next(iter(grades)),re.I) if len(grades)==1 else None
            if not match:raise ProfileError('one_original_student_grade_required')
            return str(int(match[1]))
        if exam['system']=='IELTS' and column.endswith('_name'):
            labels={'score':'Overall band score','listening':'Listening','reading':'Reading','writing':'Writing','speaking':'Speaking'}
            if column[:-5] not in labels:raise ProfileError('canonical_exam_component_required')
            return labels[column[:-5]]
        if column in {'ab_subscore','ab_subscore_name'}:
            if exam['system']!='AP' or exam['name']!='AP Calculus BC':
                raise ProfileError('calculus_bc_subscore_parent_required')
            value=profile['facts'].get(exam['score_fact_id'].rsplit('.',1)[0]+'.ab_subscore',{}).get('value')
            if type(value) is not int or not 1<=value<=5:
                raise ProfileError('explicit_ab_subscore_required')
            return 'Calculus AB SUBSCORE' if column.endswith('_name') else value
        if column=='result_release_date':
            policy=student_policy(profile,'exams.ap_result_release_policy')
            if (exam['system']!='AP' or not isinstance(policy,dict) or policy.get('rule')!='exam_board_public_schedule'
                    or key not in policy.get('exam_ids',[])):
                raise ProfileError('explicit_exam_result_release_rule_required')
            from .profile import validate_exam_release_schedule
            source_id=policy.get('schedule_source_id')
            source=profile['sources'].get(source_id,{})
            released=validate_exam_release_schedule(source_id,source)
            when=profile['facts'].get(exam.get('date_fact_id'),{}).get('value','')
            if not re.fullmatch(r'\d{4}-\d{2}(?:-\d{2})?',when) or int(when[:4])!=source['year'] or released<when[:7]+'-01':
                raise ProfileError('matching_exam_administration_schedule_required')
            return released
        if column not in {'score','date','scale'}:raise ProfileError('canonical_exam_column_required')
        fact=profile['facts'].get(exam.get('date_fact_id') if column=='date' else exam['score_fact_id'],{})
        value=fact.get('scale' if column=='scale' else 'value')
        if value is None:raise ProfileError('canonical_exam_value_missing')
        return value
    if ref.startswith('psr-average:'):
        selector,column=ref[len('psr-average:'):].rsplit(':',1)
        if column not in {'percent','scale'}:raise ProfileError('original_percentage_average_column_required')
        return average_details(profile,selector)[column]
    if ref.startswith('psr-course:'):
        record_id,column=ref[len('psr-course:'):].rsplit(':',1)
        course=next((c for c in profile['academic']['courses'] if c['record_id']==record_id),None)
        if not course:raise ProfileError('original_psr_course_required')
        raw=course['raw_cells']
        if column=='name':return raw['course_description']
        if column=='level':
            match=re.search(r'(?<!\d)(10|11|12)[^\d]*$',raw['course_code'])
            if not match:match=re.search(r'\b(10|11|12)[A-Z]?$',raw['course_description'])
            if not match:raise ProfileError('explicit_original_course_level_required')
            return match[1]
        if column=='completion_date':return original_date(raw['completion_date'])
        if column in {'result_release_date','result_pending','result_status'}:
            policy=student_policy(profile,'education.course_result_date_policy')
            if not isinstance(policy,dict) or policy.get('completed')!='psr_completion_date':raise ProfileError('explicit_course_result_date_rule_required')
            if raw['completion_date']:
                if column in {'result_pending','result_status'}:
                    if not raw['school_percent']:raise ProfileError('explicit_result_status_required')
                    return False if column=='result_pending' else 'Achieved'
                return original_date(raw['completion_date'])
            report=student_policy(profile,'education.current_year.report')
            enrollment=student_policy(profile,'education.current_year.enrollment')
            if (raw['school_percent'] or not isinstance(report,dict) or not isinstance(enrollment,list) or record_id not in enrollment
                    or not any(record_id in c.get('record_ids',[]) for c in report.get('courses',[]))):
                raise ProfileError('explicit_current_course_enrollment_required')
            expected=original_date(policy.get('in_progress'))
            return True if column=='result_pending' else 'Pending' if column=='result_status' else expected
        raise ProfileError('original_psr_course_column_required')
    if ref.startswith('school-directory:'):
        from .schools import validate_directory
        validate_directory(profile)
        parts=ref.split(':')
        if len(parts)!=3 or parts[2] not in {'name','city','region','country','ceeb'}:
            raise ProfileError('verified_school_directory_column_required')
        entry=profile.get('school_directory',{}).get('entries',{}).get(parts[1],{}).get('common_app')
        if not entry:raise ProfileError('verified_school_directory_entry_required')
        return entry[parts[2]]
    if ref.startswith('psr-school:'):
        parts=ref.split(':');school=next((s for s in profile['academic']['schools'] if s['school_id']==parts[1]),None)
        if school is None:raise ProfileError('original_psr_school_required')
        if len(parts)==3 and parts[2]=='name':return school['district_school_name_raw']
        if len(parts)!=4 or not re.fullmatch(r'0|[1-9]\d*',parts[2]) or parts[3] not in {'admit_date','withdrawal_date'}:
            raise ProfileError('original_psr_school_column_required')
        index=int(parts[2])
        if index>=len(school['enrollments']):raise ProfileError('original_psr_enrollment_required')
        raw=school['enrollments'][index].get('raw_cells',{}).get(parts[3])
        if not isinstance(raw,str) or not raw:raise ProfileError('original_psr_school_date_missing')
        months=('Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec')
        try:
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}',raw):return date.fromisoformat(raw).isoformat()
            match=re.fullmatch(r'(\d{1,2})-([A-Za-z]{3})-(\d{4})',raw)
            if not match:raise ValueError()
            return date(int(match[3]),next(i for i,m in enumerate(months,1) if m.casefold()==match[2].casefold()),int(match[1])).isoformat()
        except (ValueError,StopIteration) as exc:raise ProfileError('complete_original_psr_school_date_required') from exc
    if ref.startswith('psr-context:'):
        if ':' not in ref[len('psr-context:'):]:raise ProfileError('original_psr_context_value_required')
        key,column=ref[len('psr-context:'):].rsplit(':',1)
        context=next((c for c in profile['academic']['contexts'] if c['context_id']==key),None)
        if not context or column not in {'student_grade_raw','school_year_raw'} or not context.get(column):
            raise ProfileError('original_psr_context_value_required')
        return context[column]
    raise ProfileError('original_psr_metadata_reference_required')


def validate_path(path):
    if (not isinstance(path,list) or not 1<=len(path)<=12 or any(
            not (type(p) is int and 0<=p<=999 or isinstance(p,str) and 0<len(p)<=100) for p in path)):
        raise ProfileError('bounded_canonical_source_path_required')


def select_path(value,path):
    validate_path(path)
    try:
        for part in path:
            if isinstance(value,dict) and isinstance(part,str):value=value[part]
            elif isinstance(value,list) and type(part) is int:value=value[part]
            else:raise KeyError()
    except (KeyError,IndexError) as exc:raise ProfileError('canonical_source_path_missing') from exc
    return value
