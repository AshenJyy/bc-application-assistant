"""Validate existing UC native course editors and their observed summaries."""
import re
from urllib.parse import urlsplit

from .profile import ProfileError

BASE = 'https://apply.universityofcalifornia.edu'
EDITOR = r'/my-application/acadHistFrHighSchoolClasses/editClasses/(09|10|11|12)/[0-9]+'
LABELS = {'subject':'Subject Area/Course Category', 'class_title':'Course Name',
          'honors':'Honor Type', 'grade_system':'Grading System',
          'grade1':'Grade 1', 'grade2':'Grade 2', 'grade1Other':'Grade 1',
          'grade2Other':'Grade 2', 'subject_language_code':'Language Name', 'term':'Term System'}


def validate_course_editor(page):
    from .browser import digest
    context = page.get('uc_course_editor', {})
    parent = page.get('uc_course_parent', {})
    auxiliary = page.get('uc_academic_auxiliary', {})
    url = urlsplit(page['url'])
    match = re.fullmatch(EDITOR, url.path)
    columns = ['Subject area/Course category','Course name','Hnrs','Term',
               'G1','G2','G3','G4','Language name']
    observed = context.get('columns', [])
    if 'GRDG System' in observed: columns.insert(4, 'GRDG System')
    count = context.get('row_count')
    if (not match or url.scheme+'://'+url.netloc != BASE or url.query
            or page.get('title') != 'Enter HS classes - Academic history - UC application'
            or page.get('frames_present') or page.get('scope') or page.get('collections')
            or context.get('schema') != 'uc-course-editor/1' or context.get('grade') != match[1]
            or context.get('summary_url') != BASE+'/my-application/acadHistFrGrades/'+match[1]
            or type(count) is not int or not 1 <= count <= 100
            or not re.fullmatch(r'\d{4} - \d{4} academic year',context.get('year',''))
            or not re.fullmatch(r'[a-f0-9]{64}',context.get('context_sha256',''))
            or observed != columns or len(context.get('row_terms',[])) != count
            or any(t not in {'Semester','Full year'} for t in context['row_terms'])
            or parent.get('schema') != 'uc-course-parent/1'
            or parent.get('url') != context['summary_url'] or parent.get('row_count') != count
            or parent.get('context_sha256') != context['context_sha256']
            or not re.fullmatch(r'[a-f0-9]{64}',parent.get('summary_sha256',''))
            or auxiliary.get('schema') != 'uc-empty-comments/1'
            or auxiliary.get('page_url') != BASE+'/my-application/acadHistAddInformation'
            or auxiliary.get('values_sha256') != digest({'i:additional_comments':''})
            or not re.fullmatch(r'[a-f0-9]{64}',auxiliary.get('structure_sha256',''))):
        raise ProfileError('observed_uc_course_context_invalid')
    rows = {}
    for field in page['fields']:
        key = re.fullmatch(r'i:academics_hs_classes_add_(\d+)_(\w+)',field['key'])
        if not key or int(key[1]) >= count or key[2] not in LABELS:
            raise ProfileError('observed_uc_course_fields_invalid')
        suffix = key[2]
        if (field['label'] != LABELS[suffix] or field['disabled'] or field['readonly']
                or field['control'] != ('text' if suffix in {'class_title','grade1Other','grade2Other'} else 'select')
                or field.get('selector') != '[id="'+field['key'][2:]+'"]'
                or field.get('selector_count',1) != 1 or field.get('selector_index',0) != 0):
            raise ProfileError('observed_uc_course_fields_invalid')
        rows.setdefault(int(key[1]),set()).add(suffix)
    if set(rows) != set(range(count)):
        raise ProfileError('observed_uc_course_rows_invalid')
    for index, suffixes in rows.items():
        if (not {'subject','class_title','honors'} <= suffixes
                or ('grade_system' in suffixes) != ('GRDG System' in observed)
                or len(suffixes & {'grade1','grade1Other'}) != 1
                or len(suffixes & {'grade2','grade2Other'}) != (context['row_terms'][index] == 'Semester')):
            raise ProfileError('observed_uc_course_rows_invalid')
    if any('term' in row for row in rows.values()):
        for index, suffixes in rows.items():
            field=next((f for f in page['fields'] if f['key']==f'i:academics_hs_classes_add_{index}_term'),None)
            expected='F' if context['row_terms'][index]=='Full year' else 'S'
            if ('term' not in suffixes or field['value']!=expected or
                    [(o['value'],o['label']) for o in field['options']]!=[('','--'),('F','Full'),('S','Semester')]):
                raise ProfileError('observed_uc_course_terms_invalid')
