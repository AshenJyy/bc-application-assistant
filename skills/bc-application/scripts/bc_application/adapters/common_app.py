"""Common App common sections only; college questions/supplements fail closed."""
import calendar
import re
from urllib.parse import urlsplit

from .mit import MITAdapter,normalize,birth_date
from .uc import MANUAL


class CommonAppAdapter(MITAdapter):
    system='common_app'
    application_origin='https://apply.commonapp.org'
    official_source='https://www.commonapp.org/apply/first-year-students/'
    labels={**MITAdapter.labels,'first name':'personal.legal_given_name','last name':'personal.legal_family_name',
        'middle name':'personal.middle_name','date of birth':'personal.birth_date',
        'do you have any materials under a former legal name':'personal.has_materials_under_former_legal_name'}
    textarea_labels={'first name','last name','middle name','street','street address','address line 1','address line 2'}

    def binding(self,field,target,profile=None):
        explicit=target['field_bindings'].get(field['key'])
        if explicit: return explicit
        if field['control']=='radio': return self.labels.get(normalize(field.get('group','') or field['label']))
        return self.labels.get(normalize(field['label']))

    def binding_for_page(self,field,target,profile,page):
        path=urlsplit(page['url']).path
        if 'common_factual' in page:
            from ..common_factual import binding
            return binding(profile,page,field['key'])
        if 'common_ielts' in page:
            from ..common_ielts import CONTRACT,exam
            ref=next((f['fact'] for f in CONTRACT['fields'] if f['key']==field['key']),None)
            if ref and ref.startswith('$exam.'):
                record=exam(profile)
                return 'exams.'+record['exam_id']+ref[len('$exam'):] if record else None
            return ref
        scoped=target.get('page_field_bindings',{}).get(path,{})
        if field['key'] in scoped:return scoped[field['key']]
        # These IDs are reused for different courses across grade pages.
        # Never apply a legacy global row binding to any grade editor.
        if re.fullmatch(r'/common/13/(55|56|57|58|59)',path):return None
        explicit=target['field_bindings'].get(field['key'])
        if explicit: return explicit
        # Parent/family forms also use "First name" and "Date of birth".
        # The applicant's personal mappings apply only to the observed personal
        # section; other sections require explicit factual bindings.
        if path!='/common/3/11': return None
        return self.binding(field,target,profile)

    def display_value(self,field,ref,value):
        if ref=='personal.languages.order':return str(len(value)) if isinstance(value,list) else value
        if ref=='exams.ielts.retake_planned' and value is False:return '0'
        if ref.startswith('exams.exam:'):
            if ref.endswith('.date'):
                from datetime import date
                from ..profile import ProfileError
                try:parsed=date.fromisoformat(value)
                except (TypeError,ValueError) as exc:raise ProfileError('explicit_iso_exam_day_required') from exc
                return f'{calendar.month_name[parsed.month]} {parsed.day}, {parsed.year}'
            if field['control']=='choice_input' and type(value) in {int,float}:
                return format(value,'g').removeprefix('0') if 0<value<1 else format(value,'g')
        if ref=='exams.ielts.taken_count' and type(value) is int:return str(value)
        if ref.startswith('psr:') and ref.rsplit(':',1)[-1] in {'description','course_description'} and field['control']=='text':
            # PDF cell line wrapping is layout, not part of a one-line name.
            # Keep the original cell unchanged in the canonical academic record.
            return re.sub(r'\s+',' ',re.sub(r'-\r?\n\s*','-',value)).strip()
        if ref!='personal.birth_date': return value
        parsed=birth_date(value)
        if field['control']=='date': return parsed.isoformat()
        return f'{calendar.month_name[parsed.month]} {parsed.day}, {parsed.year}'

    def required(self,field):
        if field.get('requirement_group'):return field['value']!=''
        return super().required(field)

    def required_for_page(self,field,page):
        if 'common_factual' in page:
            from ..common_factual import field_specs
            spec=next(s for s in field_specs(page) if s['key']==field['key'])
            return spec['required'] or spec.get('fact_required',False)
        return super().required_for_page(field,page)

    def dependent_field_keys(self,page,writes):
        if page.get('common_factual',{}).get('kind')!='language':return super().dependent_field_keys(page,writes)
        changed={w['field_key'] for w in writes};rows=page['common_factual']['rows']
        from ..common_factual import field_specs
        affected={row['proficiency_id'] for row in rows if row['language_key'] in changed}
        return [f['key'] for f in field_specs(page) if f['control']=='checkbox' and f['key'].split(':')[1] in affected]

    def save_action(self,page):
        route=re.fullmatch(r'/common/(2|3|4|5|7|13)/(\d+)',urlsplit(page['url']).path)
        if not route: return None
        if page.get('scope',{}).get('kind')=='common_app_grade_dialog':
            candidates=[a for a in page['actions'] if re.fullmatch(r'Continue\s*,\s*Closes dialog',a['label']) and not a.get('disabled')]
            return candidates[0] if len(candidates)==1 else None
        expected=f'i:sectionContinue{route[2]}'
        candidates=[a for a in page['actions'] if a['key']==expected and not a.get('disabled') and
                    re.fullmatch(r'Continue(?: to next section)?',a['label'],re.I)]
        return candidates[0] if len(candidates)==1 else None

    def page_blockers(self,page):
        if not re.fullmatch(r'/common/(2|3|4|5|7|13)/\d+',urlsplit(page['url']).path):
            return [{'reason':'common_app_college_supplement_or_excluded_section'}]
        blockers=super().page_blockers(page)
        parsed=urlsplit(page['url'])
        if (parsed.scheme+'://'+parsed.netloc==self.application_origin and parsed.path!='/common/3/11'
                and page.get('scope',{}).get('kind')!='common_app_grade_dialog' and not any(tag in page for tag in ('common_ielts','common_factual'))):
            blockers.append({'reason':'observed_common_app_page_contract_required'})
        for group in page.get('requirement_groups',[]):
            fields={f['key']:f for f in page['fields']}
            present=any(fields[key]['value']!='' for key in group['field_keys'])
            na=group['kind']=='credits' and fields[group['not_applicable_key']]['value'] is True
            if not present and not na:blockers.append({'reason':'applicable_course_term_value_required','row':group['row'],'kind':group['kind']})
        return blockers

    def collection_policy(self,profile,page):
        policy=super().collection_policy(profile,page)
        if 'common_ielts' in page:policy={**policy,'fact_ids':[*policy['fact_ids'],'exams.ielts.highest_scores_confirmed']}
        return policy

    def fact_blockers(self,profile,page):
        blockers=super().fact_blockers(profile,page)
        if 'common_factual' in page:
            from ..common_factual import fact_blockers
            return blockers+fact_blockers(profile,page)
        if 'common_ielts' not in page:return blockers
        facts=profile['facts']
        if facts.get('exams.ielts.highest_scores_confirmed',{}).get('value') is not True:
            blockers.append({'reason':'current_ielts_highest_scores_confirmation_required'})
        if facts.get('exams.ielts.retake_planned',{}).get('value') is not False:
            blockers.append({'reason':'planned_ielts_configuration_unsupported'})
        count=facts.get('exams.ielts.taken_count',{}).get('value')
        if count is not None and (type(count) is not int or not 1<=count<=5):
            blockers.append({'reason':'explicit_supported_ielts_taken_count_required'})
        return blockers

    def recommendations(self,field,fact_id):
        if fact_id in {'personal.middle_name','personal.suffix'}:
            return [{'field_key':field['key'],'reason':'If this is part of your legal name, match your official documents for consistent record matching.',
                'source':self.official_source,'basis':'assistant_explanation','applicant_choice_required':True}]
        return []
