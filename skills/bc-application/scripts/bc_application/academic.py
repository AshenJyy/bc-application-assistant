"""Source references for academic reporting, independent of any browser or portal.

Reports live as factual values in the one profile. They contain record/fact
references and explicit placements, never a second set of course names or marks.
"""
import re

from .browser import digest
from .checkpoints import page_requirements
from .pages import resolve
from .profile import ProfileError

TERMS={'semester_1','semester_2','trimester_1','trimester_2','trimester_3',
       'quarter_1','quarter_2','quarter_3','quarter_4','final'}
HEADERS={'school_name','school_year','grading_scale','schedule'}
GRADE_COLUMNS={'school_percent','school_grade_symbol'}


def _fact_ref(ref):
    if (not isinstance(ref,str) or not re.fullmatch(r'(education|schedules)\.[A-Za-z0-9_:.-]+',ref)):
        raise ProfileError('explicit_academic_fact_reference_required')


def validate_report(profile,report):
    if (not isinstance(report,dict) or set(report)!={'schema','grade','transcripts'} or report['schema']!='academic-report/1'
            or report['grade'] not in {'9','10','11','12'} or not isinstance(report['transcripts'],list)
            or not 1<=len(report['transcripts'])<=25):
        raise ProfileError('academic_report_schema_required')
    records={c['record_id']:c for c in profile['academic']['courses']}
    contexts={c['context_id']:c for c in profile['academic']['contexts']}
    schools={s['school_id'] for s in profile['academic']['schools']};seen=set();keys=set();total=0
    for transcript in report['transcripts']:
        if (not isinstance(transcript,dict) or set(transcript)!={'key','psr_school_id','header_refs','courses'}
                or not isinstance(transcript['psr_school_id'],str) or transcript['psr_school_id'] not in schools
                or not isinstance(transcript['key'],str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}',transcript['key'])
                or transcript['key'] in keys or not isinstance(transcript['header_refs'],dict)
                or set(transcript['header_refs'])!=HEADERS or not isinstance(transcript['courses'],list)
                or not 1<=len(transcript['courses'])<=100):
            raise ProfileError('academic_transcript_reference_schema_required')
        keys.add(transcript['key']);total+=len(transcript['courses'])
        for ref in transcript['header_refs'].values():_fact_ref(ref)
        years=set()
        for course in transcript['courses']:
            if (not isinstance(course,dict) or set(course)!={'record_id','subject_ref','level_ref','grade_terms','credit_terms','credits_na_ref'}
                    or not isinstance(course['record_id'],str) or course['record_id'] not in records or course['record_id'] in seen):
                raise ProfileError('unique_original_academic_record_required')
            record=course['record_id'];seen.add(record)
            context=contexts.get(records[record].get('context_id'),{})
            grade=re.fullmatch(r'Grade\s+0?(\d+)',context.get('student_grade_raw',''))
            if (context.get('school_id')!=transcript['psr_school_id'] or not grade or grade[1]!=report['grade']
                    or not context.get('school_year_raw')):
                raise ProfileError('original_academic_attribution_conflict')
            years.add(context['school_year_raw'])
            for key in ('subject_ref','level_ref','credits_na_ref'):_fact_ref(course[key])
            for kind in ('grade_terms','credit_terms'):
                terms=course[kind]
                if (not isinstance(terms,dict) or not set(terms)<=TERMS or (kind=='grade_terms' and not terms)):
                    raise ProfileError('explicit_academic_term_placement_required')
                for ref in terms.values():
                    allowed=GRADE_COLUMNS if kind=='grade_terms' else {'credits'}
                    if not isinstance(ref,str):raise ProfileError('original_academic_column_reference_required')
                    if ref.startswith('psr:'):
                        try:record_ref,column=ref[4:].rsplit(':',1)
                        except ValueError as exc:raise ProfileError('original_academic_column_reference_required') from exc
                        if record_ref!=record or column not in allowed:
                            raise ProfileError('original_academic_column_reference_required')
                    elif kind=='credit_terms':_fact_ref(ref)
                    else:raise ProfileError('original_psr_mark_required')
        if len(years)!=1:raise ProfileError('original_academic_school_year_conflict')
    if total>250:raise ProfileError('bounded_academic_report_required')


def compile_report(profile,report_ref):
    """Resolve a complete requirement set before creating any application rows."""
    _fact_ref(report_ref)
    fact=profile['facts'].get(report_ref)
    if fact is None:
        return {'ready':False,'required_fact_ids':[report_ref],
            'source_gate':page_requirements(profile,fact_ids=[report_ref]),'blockers':[],'transcripts':[]}
    report=fact['value'];validate_report(profile,report)
    required=[report_ref];columns={};course_ids=[];blockers=[];transcripts=[]
    def supplied(ref,*,record=None):
        if ref.startswith('psr:'):
            rid,column=ref[4:].rsplit(':',1);columns.setdefault(rid,[]).append(column);course_ids.append(rid)
        else:required.append(ref)
        try:return resolve(profile,ref)[0]
        except ProfileError as exc:
            blockers.append({'reason':str(exc),'ref':ref,**({'record_id':record} if record else {})});return None
    for item in report['transcripts']:
        headers={key:supplied(ref) for key,ref in item['header_refs'].items()}
        if any(value is not None and (not isinstance(value,str) or not value.strip()) for value in headers.values()):
            blockers.append({'reason':'explicit_academic_header_text_required','transcript_key':item['key']})
        rows=[]
        for course in item['courses']:
            rid=course['record_id'];name=supplied(f'psr:{rid}:description',record=rid)
            row={'record_id':rid,'name':name,'subject':supplied(course['subject_ref']),
                'level':supplied(course['level_ref']),'credits_na':supplied(course['credits_na_ref']),
                'grade_terms':{term:supplied(ref,record=rid) for term,ref in course['grade_terms'].items()},
                'credit_terms':{term:supplied(ref,record=rid) for term,ref in course['credit_terms'].items()},
                'grade_columns':{term:ref.rsplit(':',1)[-1] for term,ref in course['grade_terms'].items()}}
            if any(row[key] is not None and (not isinstance(row[key],str) or not row[key].strip()) for key in ('subject','level')):
                blockers.append({'reason':'explicit_academic_classification_required','record_id':rid})
            if type(row['credits_na']) is not bool:
                blockers.append({'reason':'explicit_credits_applicability_required','record_id':rid})
            elif row['credits_na'] and course['credit_terms'] or row['credits_na'] is False and not course['credit_terms']:
                blockers.append({'reason':'explicit_applicable_credit_terms_required','record_id':rid})
            if any(value is not None and (isinstance(value,bool) or not isinstance(value,(str,int,float)) or str(value)=='')
                    for value in [*row['grade_terms'].values(),*row['credit_terms'].values()]):
                blockers.append({'reason':'original_academic_term_value_required','record_id':rid})
            rows.append(row)
        transcripts.append({'key':item['key'],'headers':headers,'courses':rows})
    required=list(dict.fromkeys(required));course_ids=list(dict.fromkeys(course_ids))
    columns={rid:list(dict.fromkeys(cols)) for rid,cols in columns.items()}
    gate=page_requirements(profile,fact_ids=required,course_ids=course_ids,record_columns=columns)
    return {'ready':gate['data_ready'] and not blockers,'grade':report['grade'],'transcripts':transcripts,
        'required_fact_ids':required,'required_course_ids':course_ids,'required_record_columns':columns,
        'source_gate':gate,'blockers':blockers,
        'source_fingerprint':digest({'psr_sha256':profile['academic_sha256'],
            'facts':{ref:profile['facts'].get(ref) for ref in required}})}
