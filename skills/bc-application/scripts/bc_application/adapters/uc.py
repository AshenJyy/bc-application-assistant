"""Observed UC factual controls; never guess classifications or convert grades."""
from __future__ import annotations

import re

MANUAL = re.compile(r"essay|personal insight|declar|certif|attest|signature|submit|payment|credit card|"
                    r"invit|recommendation request|why (?:are|do|did|would)|describe|explain|reflect|"
                    r"greatest|most meaningful|leadership|agree to|waiv|consent|authoriz|authoris|i permit|"
                    r"i (?:have reported all|confirm|affirm|acknowledge|agree|understand|have read|have reviewed)|"
                    r"i['’]ve finished|"
                    r"indicate that you have reported all", re.I)


class UCAdapter:
    system = "uc"
    application_origin = "https://apply.universityofcalifornia.edu"
    official_source = "https://admission.universityofcalifornia.edu/admission-requirements/international-applicants/applying-for-admission/"
    known = {
        "firstName":"personal.legal_given_name", "middleName":"personal.middle_name",
        "lastName":"personal.legal_family_name", "suffixName":"personal.suffix",
        "hasLivedName":"personal.has_lived_name", "otherNames":"personal.has_previous_legal_name",
        "birthDateMM":"personal.birth_month", "birthDateDD":"personal.birth_day",
        "birthDateYYYY":"personal.birth_year", "birthCountryCode":"personal.birth_country",
        "birthCity":"personal.birth_city", "hasAttendedCaPublicSchool":"education.attended_california_public_school",
    }
    # Questions are required by the observed page even where the HTML omits required.
    required_names = {"firstName", "lastName", "hasLivedName", "otherNames", "birthDateMM",
                      "birthDateDD", "birthDateYYYY", "birthCountryCode", "birthCity", "hasAttendedCaPublicSchool"}

    def binding(self, field: dict, target: dict, profile: dict | None = None) -> str | None:
        ref = target["field_bindings"].get(field["key"], self.known.get(field.get("name")))
        if ref in {"personal.birth_month","personal.birth_day","personal.birth_year"} and profile and "personal.birth_date" in profile["facts"]:
            return "personal.birth_date"
        return ref

    def binding_for_page(self,field,target,profile,page):
        from urllib.parse import urlsplit
        scoped=target.get('page_field_bindings',{}).get(urlsplit(page['url']).path,{})
        if 'uc_course_editor' in page:
            return scoped.get(field['key'])
        if 'uc_factual' in page and field['key'] not in scoped:
            from ..uc_factual import contract
            spec=contract(page)
            ref=next((f['fact'] for f in spec['fields'] if f['key']==field['key']),None)
            if ref and ref.startswith('$exam.'):
                exams=[e for e in profile['exams'].values() if e['system']==spec['exam_system'] and e['name']==spec['exam_name']]
                if len(exams)!=1:return None
                return 'exams.'+exams[0]['exam_id']+ref[len('$exam'):]
            return ref
        if field['key'] in scoped:
            target={**target,'field_bindings':{**target['field_bindings'],**scoped}}
        return self.binding(field,target,profile)

    def display_value(self, field: dict, ref: str, value: object) -> object:
        if ref.startswith('exams.exam:'):
            if ref.endswith('.date') and field['key'] in {'i:takenMonth','i:takenYear'}:
                from ..profile import validate_exam_date
                import calendar
                validate_exam_date(value)
                return calendar.month_name[int(value[5:7])] if field['key']=='i:takenMonth' else value[:4]
            if ref.rsplit('.',1)[-1] in {'score','listening','reading','writing','speaking'} and field['key'].startswith('i:ielts'):
                if type(value) in {int,float}:return f'{value:.1f}'
        if ref.startswith('psr:') and ref.endswith(':description'):
            return re.sub(r'\s+',' ',str(value)).strip()
        # The portal's exact country label is a lossless display alias for the
        # explicitly supplied country, not a different canonical nationality.
        if ref in {'personal.birth_country','personal.citizenship','address.permanent.country','address.mailing.country'} and value=='China':
            return 'China, Peoples Republic of'
        if ref in {'personal.current_us_visa','personal.planned_us_visa'} and isinstance(value,str):
            matches=[o['label'] for o in field['options'] if o['label'].startswith(value+' - ') and not o['disabled']]
            if len(matches)==1:return matches[0]
        if ref=='education.first_language' and field['key']=='i:lang_first_code' and value=='Chinese':return 'Other language'
        if ref != "personal.birth_date":
            return value
        from datetime import date
        import calendar
        from ..profile import ProfileError
        try: parsed = date.fromisoformat(value)
        except (TypeError,ValueError) as exc:
            raise ProfileError("explicit_iso_birth_date_required") from exc
        return {"birthDateMM":calendar.month_name[parsed.month], "birthDateDD":f"{parsed.day:02}",
                "birthDateYYYY":str(parsed.year)}.get(field.get("name"),value)

    def required(self, field: dict) -> bool:
        return bool(field.get("required") or field.get("name") in self.required_names)

    def required_for_page(self, field: dict, page: dict) -> bool:
        if 'uc_course_editor' in page:
            return True
        if 'uc_factual' in page:
            from ..uc_factual import contract
            return self.required(field) or next(f['required'] for f in contract(page)['fields'] if f['key']==field['key'])
        return self.required(field)

    def collection_policy(self, profile: dict, page: dict) -> dict:
        return {"allowed":not page.get('collections'), "fact_ids":[]}

    def fact_blockers(self, profile: dict, page: dict) -> list[dict]:
        if 'uc_course_editor' in page:
            terms=page['uc_course_editor']['row_terms']
            if profile['facts'].get('education.uc_ap_reporting_term',{}).get('value')=='Full year':
                if any(f['value']=='AP' and terms[int(re.search(r'add_(\d+)_',f['key'])[1])]!='Full year'
                       for f in page['fields'] if f['key'].endswith('_honors')):
                    return [{'reason':'uc_ap_yearly_school_and_course_setup_required'}]
        return []

    def dependent_field_keys(self, page: dict, writes: list[dict]) -> list[str]:
        if self.system!='uc':return []
        fields={f['key']:f for f in page['fields']}
        parents={fields[w['field_key']].get('name') for w in writes}
        dependencies={'birthDateDD':{'birthDateMM','birthDateYYYY'},'birthCity':{'birthCountryCode'}}
        # UC rebuilds dependent controls after native changes. Reapply only
        # already-resolved factual children, after all their parents.
        return [f['key'] for f in page['fields'] if dependencies.get(f.get('name'),set()) & parents]

    def manual(self, field: dict) -> bool:
        citizenship='What will your citizenship status be on the date you submit this application? *'
        if field['key']=='n:citizenshipStatus' and field['control']=='radio' and field['label']==field.get('group')==citizenship:
            return False
        return bool(MANUAL.search(field["label"] + " " + field.get("group", "")) or
                    field["control"] in {"unsupported","textarea"})

    def skip_optional_unsupported(self, field: dict) -> bool:
        return False

    def skip_blank_optional_manual(self, field: dict, page: dict) -> bool:
        return False

    def page_blockers(self, page: dict) -> list[dict]:
        blockers=[{"reason":"manual_application_section"}] if MANUAL.search(page.get("title", "")) else []
        # Some UC summary/selection pages expose a Save button but no native
        # required controls. An empty plan cannot establish their requirements.
        from urllib.parse import urlsplit
        parsed=urlsplit(page['url'])
        if (self.system=='uc' and parsed.scheme+'://'+parsed.netloc==self.application_origin
                and parsed.path!='/my-application/accountPersonal'
                and not any(tag in page for tag in ('uc_course_editor','uc_factual','uc_course_refill','uc_school_terms'))):
            blockers.append({'reason':'observed_uc_page_contract_required'})
        return blockers

    def save_action(self, page: dict) -> dict | None:
        candidates = [a for a in page["actions"] if not a.get("disabled") and
                      re.fullmatch(r"save\s*(?:&\s*continue|and continue|draft)?", a["label"].strip(), re.I)]
        # An action's type=submit is not permission to submit an application.
        # UC's actual draft-save is an input[type=submit] labelled Save&continue.
        return candidates[0] if len(candidates) == 1 else None

    def recommendations(self, field: dict, fact_id: str | None) -> list[dict]:
        if fact_id in {"personal.middle_name", "personal.suffix"}:
            return [{"field_key":field["key"], "reason":"If present on your legal records, use the same full name to help match records.",
                     "source":self.official_source, "basis":"assistant_explanation", "applicant_choice_required":True}]
        return []
