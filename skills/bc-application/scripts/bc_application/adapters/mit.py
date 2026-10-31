"""MIT First-Year observed labels; no question UUIDs or guessed classifications."""
import calendar
import re
from datetime import date

from .uc import UCAdapter,MANUAL
from ..profile import ProfileError

COURSEWORK_NOTES = (
    'List any course(s) with standardized exams (A-level, Baccalauréat, CAPEs, etc.) taken or underway. '
    '(If you have taken the exam, please list the test date and score.) Advanced Placement or '
    'International Baccalaureate exams should be reported on the next page.',
    "If there is anything we should know about your school's course offerings, extenuating circumstances "
    "regarding your coursework or access to standardized testing, or school's grading system, please "
    'use the space below.optional; 100 words or fewer',
)
STEM_SUBJECTS = {'calculus','physics','biology','chemistry'}
STEM_STATUS_LABELS = {'taken':'Taken','in_progress_or_planned':'In progress/will take',
                      'will_not_take':'Will not take'}
CLASSES_HEADER = 'Subject Category | Year Taken | Level | Class Name | Grade Received'
CLASSES_INSTRUCTION = ('This section is only required for students in the U.S. or who attend U.S.-based school systems. '
    'Report all classes you have taken or will take in high school or for high school credit.')
STEM_INSTRUCTION = ('All students are required to fill out this section. Please indicate the status and year taken '
    '(or to be taken) of each class listed below. If you took these classes in a year that is not listed, or you '
    'did not take the class, you can leave the year blank. If you have taken a class multiple times, please '
    'list the year you most recently took it.')


def normalize(label: str) -> str:
    label=re.sub(r'optional.*$','',label,flags=re.I)
    return ' '.join(re.sub(r'[^a-z0-9]+',' ',label.lower()).split())


def birth_date(value):
    try: return date.fromisoformat(value)
    except (TypeError,ValueError) as exc:
        raise ProfileError('explicit_iso_birth_date_required') from exc


class MITAdapter(UCAdapter):
    system='mit'
    application_origin='https://apply.mitadmissions.org'
    official_source='https://apply.mitadmissions.org/portal/apply'
    required_names=set()
    labels={'legal first given':'personal.legal_given_name','legal last family':'personal.legal_family_name',
        'middle':'personal.middle_name','suffix':'personal.suffix','preferred first name':'personal.preferred_given_name',
        'preferred last name':'personal.preferred_family_name','current email':'contact.email','mobile':'contact.mobile',
        'birth country':'personal.birth_country','birth city':'personal.birth_city','birth region state':'personal.birth_region',
        'citizenship':'personal.citizenship','legal sex':'personal.legal_sex',
        'preferred first name to use in communications':'personal.communication_name_choice'}
    textarea_labels={'street','legal first given','legal last family','middle'}

    def binding_for_page(self,field,target,profile,page):
        for pair in page.get('mit_coursework',{}).get('subject_year_pairs',[]):
            for part in ('status','year'):
                if field['key']==pair[part+'_key']:
                    return f'education.subjects.{pair["subject"]}.{part}'
        return super().binding_for_page(field,target,profile,page)

    def required_for_page(self,field,page):
        return self.required(field) or any(field['key']==p['year_key'] for p in
            page.get('mit_coursework',{}).get('subject_year_pairs',[]))

    def page_blockers(self,page):
        blockers=super().page_blockers(page)
        if (normalize(page.get('title','')) in {'self reported coursework','synthetic mit self reported coursework'}
                and 'mit_coursework' not in page):
            blockers.append({'reason':'mit_coursework_semantic_context_required'})
        return blockers

    def collection_policy(self,profile,page):
        refs=['education.current_school_country','education.us_based_school_system']
        collections=page.get('collections',[])
        allowed=(self.system=='mit' and 'mit_coursework' in page and len(collections)==1 and
            collections[0]=={'kind':'editable_table','label':CLASSES_HEADER,'row_count':0,'editor_control_count':1} and
            profile['facts'].get(refs[0],{}).get('value')=='Canada' and
            profile['facts'].get(refs[1],{}).get('value') is False)
        return {'allowed':allowed or not collections,'fact_ids':refs if collections and 'mit_coursework' in page else [],
            **({'kind':'mit_non_us_empty_classes'} if allowed else {})}

    def fact_blockers(self,profile,page):
        if 'mit_coursework' not in page:return []
        return [{'reason':'contradictory_subject_status_and_year','subject':s} for s in STEM_SUBJECTS
            if profile['facts'].get(f'education.subjects.{s}.status',{}).get('value')=='will_not_take'
            and profile['facts'].get(f'education.subjects.{s}.year',{}).get('value') in {'9th','10th','11th','12th'}]

    def binding(self,field,target,profile=None):
        explicit=target['field_bindings'].get(field['key'])
        if explicit: return explicit
        label=normalize(field['label']); group=normalize(field.get('group',''))
        if (field['control']=='select' and label in STEM_SUBJECTS and
                {o['label'] for o in field['options'] if o['value']} == set(STEM_STATUS_LABELS.values())):
            return f'education.subjects.{label}.status'
        if group.startswith('birthdate') and label in {'month','day','year'}: return 'personal.birth_date'
        if field['control']=='radio' and group.startswith('preferred first name to use in communications'):
            return 'personal.communication_name_choice'
        if group.startswith('legal sex'): return 'personal.legal_sex'
        for prefix in ('permanent','mailing'):
            if group.startswith(prefix+' address'):
                part={'country':'country','street':'street','city':'city','region':'region','province':'region','postal code':'postal_code'}.get(label)
                if part: return f'address.{prefix}.{part}'
        return self.labels.get(label)

    def display_value(self,field,ref,value):
        if ref in {f'education.subjects.{subject}.year' for subject in STEM_SUBJECTS}:
            if not isinstance(value,str) or value not in {'9th','10th','11th','12th','not_listed_or_not_taken'}:
                raise ProfileError('explicit_subject_coursework_year_required')
            return '' if value=='not_listed_or_not_taken' else value
        if ref in {f'education.subjects.{subject}.status' for subject in STEM_SUBJECTS}:
            if not isinstance(value,str) or value not in STEM_STATUS_LABELS:
                raise ProfileError('explicit_subject_coursework_status_required')
            return STEM_STATUS_LABELS[value]
        if ref!='personal.birth_date': return value
        parsed=birth_date(value); label=normalize(field['label'])
        return {'month':calendar.month_name[parsed.month],'day':str(parsed.day),'year':str(parsed.year)}.get(label,value)

    def manual(self,field):
        if MANUAL.search(field['label']+' '+field.get('group','')): return True
        if field['control']=='textarea': return normalize(field['label']) not in self.textarea_labels
        return field['control']=='unsupported'

    def skip_optional_unsupported(self,field):
        # Known optional controls may stay untouched; narrative exceptions are
        # separately restricted below. Never enter religious/self-identity choices.
        label=normalize(field['label'])
        return field['control']=='unsupported' and (label=='suffix' or label=='religious preference or affiliation')

    def skip_blank_optional_manual(self,field,page):
        # Only these observed optional notes may remain empty on this page.
        # A selected, required, edited or nonempty narrative still stops saving.
        return (self.system=='mit' and normalize(page.get('title','')) in
                {'self reported coursework','synthetic mit self reported coursework'} and
                field['control']=='textarea' and field['value']=='' and
                not self.required(field) and not field.get('invalid') and
                normalize(field['label']) in {normalize(label) for label in COURSEWORK_NOTES} and
                not MANUAL.search(field['label']+' '+field.get('group','')))

    def recommendations(self,field,fact_id):
        if fact_id=='contact.email':
            return [{'field_key':field['key'],'reason':'Use an email you check throughout the application process and keep MIT messages out of spam so you receive updates.',
                'source':self.official_source,'basis':'assistant_explanation','applicant_choice_required':True}]
        return []
