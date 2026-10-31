"""Portable observed-page contract. No browser internals or network calls."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Protocol
from urllib.parse import urlsplit

from .profile import ProfileError


class BrowserPort(Protocol):
    def observe(self) -> dict: ...
    def write(self, writes: list[dict]) -> None: ...
    def save_draft(self, action: dict) -> None: ...
    def revisit(self, url: str) -> None: ...


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def origin(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.scheme not in {"https", "http"}:
        raise ProfileError("observed_url_unsupported")
    return f"{parsed.scheme}://{parsed.netloc}"


def common_question_id(page: dict, field: dict) -> str | None:
    parsed = urlsplit(page['url'])
    factual=page.get('common_factual',{}).get('schema')=='common-factual-page/1' and parsed.path in {'/common/3/16','/common/5/26','/common/13/58'}
    if (origin(page['url']) not in {'https://apply.commonapp.org','http://127.0.0.1:8765','http://localhost:8765'}
            or not (parsed.path=='/common/3/11' or factual or parsed.path=='/common/2/10' and page.get('common_ielts',{}).get('schema')=='common-ielts-page/1') or field['control'] != 'radio'
            or not re.fullmatch(r'mat-radio-group-\d+',field.get('name',''))
            or not field['label'] or field.get('group') != field['label'] or len(field['options']) < 2):
        return None
    matches = [re.fullmatch(r'\[id="option_ques_(\d+)_\d+-input"\]',o.get('selector') or '') for o in field['options']]
    if (not all(matches) or len({m[1] for m in matches}) != 1
            or field.get('selector') != field['options'][0]['selector']
            or any(o.get('selector_count',1) != 1 or o.get('selector_index',0) != 0 for o in [field,*field['options']])):
        return None
    return matches[0][1]


def validate_mit_coursework(page: dict) -> None:
    from .adapters.mit import CLASSES_INSTRUCTION, STEM_INSTRUCTION, STEM_SUBJECTS, STEM_STATUS_LABELS, normalize
    context=page['mit_coursework']
    if (origin(page['url']) not in {'https://apply.mitadmissions.org','http://127.0.0.1:8765','http://localhost:8765'}
            or urlsplit(page['url']).path!='/apply/frm'
            or normalize(page.get('title','')) not in {'self reported coursework','synthetic mit self reported coursework'}
            or context.get('schema')!='mit-coursework/1'
            or context.get('classes_instruction')!=CLASSES_INSTRUCTION or context.get('stem_instruction')!=STEM_INSTRUCTION):
        raise ProfileError('observed_mit_coursework_context_invalid')
    pairs=context.get('subject_year_pairs',[])
    if len(pairs)!=4 or {p.get('subject') for p in pairs}!=STEM_SUBJECTS:
        raise ProfileError('observed_mit_subject_pairs_invalid')
    used=[];by_key={f['key']:f for f in page['fields']}
    for pair in pairs:
        status=by_key.get(pair.get('status_key'),{});year=by_key.get(pair.get('year_key'),{})
        if (status.get('control')!='select' or normalize(status.get('label',''))!=pair['subject']
                or {o['label'] for o in status['options'] if o['value']}!=set(STEM_STATUS_LABELS.values())
                or year.get('control')!='select' or normalize(year.get('label',''))!='year'
                or {o['label'] for o in year['options'] if o['value']}!={'9th','10th','11th','12th'}):
            raise ProfileError('observed_mit_subject_pairs_invalid')
        used.extend([pair['status_key'],pair['year_key']])
    if len(set(used))!=8:
        raise ProfileError('observed_mit_subject_pairs_invalid')


def validate_mit_state(state: dict, page: dict) -> None:
    if (origin(page['url'])!='https://apply.mitadmissions.org' or 'mit_coursework' not in page
            or state.get('page_url')!=page['url'] or state.get('schema')!='observed-state/1'
            or state.get('coverage')!='mit_visible_review_and_draft'
            or state.get('review_url')!='https://apply.mitadmissions.org/apply/review'
            or state.get('portal_url')!='https://apply.mitadmissions.org/portal/apply'
            or state.get('application_status')!='In Progress'):
        raise ProfileError('observed_mit_state_invalid')
    sections={'Getting started','Personal information','Application information','Family information','Schools',
        'Academic history','Self-reported coursework','Test scores','Test summary','Essays',
        'Activities and distinctions','Jobs','Recommendations','Certification','Fee waiver request'}
    for kind in ('errors','warnings'):
        items=state.get(kind)
        if not isinstance(items,list) or len(items)>100:
            raise ProfileError('observed_mit_state_invalid')
        for item in items:
            if (item.get('section') not in sections or not isinstance(item.get('message'),str)
                    or not 1<=len(item['message'])<=1000
                    or not re.fullmatch(r'(frm\?[a-f0-9-]{36}|tes)',item.get('href',''))):
                raise ProfileError('observed_mit_state_invalid')


def validate_common_state(state: dict) -> None:
    if (not isinstance(state,dict) or state.get('schema')!='observed-state/1'
            or state.get('coverage')!='common_app_visible_navigation'
            or not isinstance(state.get('items'),list) or not 1<=len(state['items'])<=50):
        raise ProfileError('observed_state_metadata_invalid')
    keys=[]
    for item in state['items']:
        if (not isinstance(item,dict) or not isinstance(item.get('key'),str)
                or not re.fullmatch(r'(secondaryNavItem\d+|tertiaryNavItem\d+_\d+)',item['key'])
                or item.get('status') not in {'complete','in progress','incomplete','not started'}):
            raise ProfileError('observed_state_metadata_invalid')
        keys.append(item['key'])
    if len(keys)!=len(set(keys)) or state.get('current_page_key') not in keys:
        raise ProfileError('observed_state_metadata_invalid')


def validate_uc_state(state: dict, page: dict) -> None:
    base='https://apply.universityofcalifornia.edu'
    courses='uc_course_editor' in page
    school_terms=page.get('uc_school_terms',{}).get('schema')=='uc-school-terms/1'
    refill=page.get('uc_course_refill',{}).get('schema')=='uc-course-refill/1'
    factual='uc_factual' in page
    if factual:
        from .uc_factual import validate_factual
        validate_factual(page)
    if refill:
        from .uc_course_refill import validate_native
        validate_native(page,page['uc_course_refill']['context'])
    if courses:
        from .uc_courses import validate_course_editor
        validate_course_editor(page)
    if school_terms:
        from .uc_term_setup import school_form_blockers
        native={k:v for k,v in page.items() if k not in {'state_metadata','uc_school_terms'}}
        if school_form_blockers(native):raise ProfileError('observed_uc_school_terms_invalid')
    if ((not courses and not school_terms and not refill and not factual and page['url']!=base+'/my-application/accountPersonal') or state.get('schema')!='observed-state/1'
            or state.get('coverage')!='uc_visible_review_and_draft' or state.get('page_url')!=page['url']
            or state.get('review_url')!=base+'/my-application/reviewSubmit'
            or state.get('status_url')!=base+'/my-application/appStatus'
            or state.get('term')!='Fall quarter/semester 2027' or state.get('draft_marker')!='Open application'):
        raise ProfileError('observed_uc_state_invalid')
    expected={'About you','Campuses & majors','Academic history','Test scores','Activities & awards',
        'Scholarships & support programs','Personal insight'}
    sections=state.get('sections',[])
    if len(sections)!=7 or {s.get('label') for s in sections}!=expected:
        raise ProfileError('observed_uc_state_invalid')
    hrefs=[]
    for section in sections:
        if section.get('completion_text') not in {'','Section Complete'} or not isinstance(section.get('pages'),list) or not 1<=len(section['pages'])<=30:
            raise ProfileError('observed_uc_state_invalid')
        for item in section['pages']:
            if (not re.fullmatch(r'/my-application/[a-zA-Z0-9/-]+(?:\?testType=\d+)?',item.get('href',''))
                    or not re.fullmatch(r'(Edit|To do) .{1,150}',item.get('label',''))):
                raise ProfileError('observed_uc_state_invalid')
            hrefs.append(item['href'])
    if len(hrefs)!=len(set(hrefs)):
        raise ProfileError('observed_uc_state_invalid')


def validate_observation(page: dict) -> None:
    try:
        origin(page["url"])
        if page["schema"] != "observed-page/1" or not isinstance(page["fields"], list):
            raise ProfileError("observed_page_schema_unsupported")
        keys = [f["key"] for f in page["fields"]]
        actions = [a["key"] for a in page["actions"]]
        if len(keys) != len(set(keys)) or len(actions) != len(set(actions)):
            raise ProfileError("ambiguous_observed_controls")
        if 'mit_coursework' in page:
            validate_mit_coursework(page)
        if 'uc_course_editor' in page:
            from .uc_courses import validate_course_editor
            validate_course_editor(page)
        if 'uc_factual' in page:
            from .uc_factual import validate_factual
            validate_factual(page)
        if 'common_ielts' in page:
            from .common_ielts import validate
            validate(page)
        if 'common_factual' in page:
            from .common_factual import validate
            validate(page)
        if 'generic_form' in page:
            from .generic_forms import validate
            validate(page)
        if 'common_ielts' in page and 'common_factual' in page:raise ProfileError('ambiguous_common_page_contract')
        creation=page.get('scope',{}).get('kind')=='common_app_grade_creation'
        scoped=page.get('scope',{}).get('kind')=='common_app_grade_dialog' or creation
        if 'scope' in page:
            if (not scoped or page['scope'].get('name')!='Courses & Grades'
                    or origin(page['url']) not in {'https://apply.commonapp.org','http://127.0.0.1:8765','http://localhost:8765'}
                    or not re.fullmatch(r'/common/13/(55|56|57|58|59)',urlsplit(page['url']).path)
                    or not page['scope'].get('heading','').startswith('Courses & Grades')):
                raise ProfileError('observed_grade_scope_invalid')
        if 'collections' in page:
            collections=page['collections']
            if not isinstance(collections,list) or len(collections)>50:
                raise ProfileError('observed_collections_invalid')
            for collection in collections:
                if (not isinstance(collection,dict) or collection.get('kind')!='editable_table'
                        or not isinstance(collection.get('label'),str) or not 1<=len(collection['label'])<=1000
                        or type(collection.get('row_count')) is not int or not 0<=collection['row_count']<=1000
                        or type(collection.get('editor_control_count')) is not int or not 1<=collection['editor_control_count']<=1000):
                    raise ProfileError('observed_collections_invalid')
        if 'state_metadata' in page:
            state=page['state_metadata']
            if isinstance(state,dict) and state.get('coverage')=='mit_visible_review_and_draft':
                validate_mit_state(state,page)
            elif isinstance(state,dict) and state.get('coverage')=='uc_visible_review_and_draft':
                validate_uc_state(state,page)
            else:
                validate_common_state(state)
        identities = set()
        for field in page["fields"]:
            if not field["key"] or not isinstance(field["label"], str) or "value" not in field:
                raise ProfileError("observed_field_incomplete")
            if field["control"] not in {"text", "textarea", "email", "tel", "number", "date", "select", "radio", "checkbox", "material_select", "choice_input", "unsupported"}:
                raise ProfileError("observed_control_unsupported")
            if field['control']=='choice_input' and not any(tag in page for tag in ('common_ielts','common_factual')):
                raise ProfileError('observed_choice_input_contract_required')
            if field['control']=='material_select' and (not scoped or field['options']):
                raise ProfileError('observed_material_scope_invalid')
            if 'identity_kind' in field:
                question = common_question_id(page,field)
                if (field['identity_kind'] != 'common_app_question_radio' or question is None
                        or field['key'] != f'r:ques_{question}'):
                    raise ProfileError('observed_radio_identity_invalid')
            for identified in [field] + (field["options"] if field["control"] == "radio" else []):
                if "selector_count" in identified or "selector_index" in identified:
                    count,index = identified.get("selector_count"),identified.get("selector_index")
                    if (type(count) is not int or type(index) is not int or count < 0
                            or (identified.get("selector") and not 0 <= index < count)
                            or (not identified.get("selector") and (count,index) != (0,-1))):
                        raise ProfileError("observed_selector_identity_invalid")
            for identified in field["options"] if field["control"] == "radio" else [field]:
                if identified.get("selector"):
                    identity=(identified["selector"],identified.get("selector_index",0))
                    if identity in identities:
                        raise ProfileError("ambiguous_observed_controls")
                    identities.add(identity)
            if field["control"] in {"select", "radio"}:
                values = [o["value"] for o in field["options"]]
                if len(values) != len(set(values)):
                    raise ProfileError("ambiguous_observed_options")
        if scoped:
            groups=page.get('requirement_groups')
            if not isinstance(groups,list) or (not groups and not creation) or len(groups)>(500 if creation else 200):
                raise ProfileError('observed_term_groups_invalid')
            pairs=set();grouped=set();by_key={f['key']:f for f in page['fields']}
            for rule in groups:
                pair=(rule.get('row'),rule.get('kind'))
                if (not re.fullmatch(r'T\d+C\d+',pair[0] or '') or pair[1] not in {'grades','credits'}
                        or pair in pairs or not isinstance(rule.get('field_keys'),list) or not 1<=len(rule['field_keys'])<=5):
                    raise ProfileError('observed_term_groups_invalid')
                pairs.add(pair)
                for key in rule['field_keys']:
                    f=by_key.get(key)
                    row_match=re.fullmatch(r'T(\d+)C(\d+)',pair[0])
                    prefix=f'Transcript {row_match[1]}, Course {row_match[2]}, '
                    suffix=(f or {}).get('label','').removeprefix(prefix).removesuffix('undefined')
                    term=(r'(Semester [12]|Trimester [123]|Quarter [1-4]|Final)( Grade)?' if pair[1]=='grades'
                          else r'(Semester [12]|Trimester [123]|Quarter [1-4]) Credit|Final Credits')
                    if (key in grouped or not f or f.get('required') is not False
                            or not f['label'].startswith(prefix) or not re.fullmatch(term,suffix)
                            or f['control'] not in ({'text','material_select'} if pair[1]=='grades' else {'text','number'})
                            or f.get('requirement_group')!={'row':pair[0],'kind':pair[1]}):
                        raise ProfileError('observed_term_groups_invalid')
                    grouped.add(key)
                if pair[1]=='credits':
                    na=by_key.get(rule.get('not_applicable_key'))
                    if not na or na['control']!='checkbox' or na['label']!=prefix+'Credits not applicable':
                        raise ProfileError('observed_term_groups_invalid')
            if any((row,kind) not in pairs for row,_ in pairs for kind in ('grades','credits')):
                raise ProfileError('observed_term_groups_invalid')
            if any(f.get('requirement_group') and f['key'] not in grouped for f in page['fields']):
                raise ProfileError('observed_term_groups_invalid')
        if creation:
            from .common_academic import validate_layout
            validate_layout(page)
        choices=page.get('choice_observations',{})
        if not isinstance(choices,dict):raise ProfileError('observed_material_choices_invalid')
        for key,options in choices.items():
            field=next((f for f in page['fields'] if f['key']==key),None)
            if not field or field['control'] not in {'material_select','choice_input'} or not isinstance(options,list) or not 1<=len(options)<=500:
                raise ProfileError('observed_material_choices_invalid')
            labels=[]
            for option in options:
                if (not isinstance(option,dict) or not isinstance(option.get('label'),str)
                        or option.get('value')!=option['label'] or type(option.get('disabled')) is not bool):
                    raise ProfileError('observed_material_choices_invalid')
                labels.append(option['label'])
            if len(labels)!=len(set(labels)):raise ProfileError('ambiguous_observed_options')
        if 'editor_state' in page:
            parent=page['editor_state']
            if (not scoped or parent.get('schema')!='grade-parent/1' or parent.get('url')!=page['url']
                    or type(parent.get('completion_checked')) is not bool
                    or any(not re.fullmatch(r'[a-f0-9]{64}',parent.get(k,'')) for k in
                        ('controls_sha256','values_sha256','summary_sha256'))
                    or parent.get('state_metadata')!=page.get('state_metadata')
                    or parent.get('reopen_action',{}).get('key')!='i:addCG'):
                raise ProfileError('observed_grade_parent_invalid')
    except (KeyError, TypeError, AttributeError) as exc:
        raise ProfileError("observed_page_structure_invalid") from exc


def structure(page: dict) -> dict:
    """Store control metadata without a second copy of current personal values."""
    if 'generic_form' in page:
        tag=page['generic_form'];scope=tag['scope']
        return {'schema':page['schema'],'url':page['url'],'title':page.get('title',''),'frames_present':page.get('frames_present',False),
            'collections':page.get('collections',[]),'generic_form':{**tag,'scope':{k:scope[k] for k in ('selector_count','selector_index')},
                **({'dialog':{k:tag['dialog'][k] for k in ('name','selector_count')}} if tag.get('dialog') else {}),
                **({'record_collections':[{k:v for k,v in c.items() if k!='selector'} for c in tag['record_collections']]} if tag.get('record_collections') else {})},
            'fields':[{**{k:v for k,v in f.items() if k not in {'value','invalid','selector','name'}},
                'options':[{k:v for k,v in o.items() if k not in {'selector','native_value'}} for o in f['options']]} for f in page['fields']],
            'actions':[{k:v for k,v in a.items() if k!='selector'} for a in page['actions']]}
    return {"schema":page["schema"], "url":page["url"], "title":page.get("title", ""),
            "frames_present":page.get("frames_present", False),
            "collections":page.get('collections',[]),
            **({'mit_coursework':page['mit_coursework']} if 'mit_coursework' in page else {}),
            **({'uc_course_editor':page['uc_course_editor']} if 'uc_course_editor' in page else {}),
            **({'uc_academic_auxiliary':page['uc_academic_auxiliary']} if 'uc_academic_auxiliary' in page else {}),
            **({'uc_school_terms':page['uc_school_terms']} if 'uc_school_terms' in page else {}),
            **({'uc_course_refill':page['uc_course_refill']} if 'uc_course_refill' in page else {}),
            **({'uc_factual':page['uc_factual']} if 'uc_factual' in page else {}),
            **({'common_ielts':page['common_ielts']} if 'common_ielts' in page else {}),
            **({'common_factual':page['common_factual']} if 'common_factual' in page else {}),
            **({'common_academic':page['common_academic']} if 'common_academic' in page else {}),
            **({'academic_layout':page['academic_layout']} if 'academic_layout' in page else {}),
            **({'generic_form':page['generic_form']} if 'generic_form' in page else {}),
            **({'scope':page['scope'],'requirement_groups':page.get('requirement_groups',[])} if 'scope' in page else {}),
            "fields":[{k:v for k,v in f.items() if k not in {"value", "invalid"}
                       and not (k == 'name' and f.get('identity_kind') == 'common_app_question_radio')}
                      for f in page["fields"]],
            "actions":page["actions"]}


def values(page: dict) -> dict:
    return {f["key"]:f["value"] for f in page["fields"]}


def permission_gate(context: dict, page: dict, allowed_origin: str) -> None:
    synthetic = context.get('synthetic_test') is True and origin(page['url']) in {
        'http://127.0.0.1:8765','http://localhost:8765'}
    if (context.get("browser_family") not in {"chrome", "edge"} or
        context.get("transport") != "extension" or context.get("origin") != origin(page["url"]) or
        context.get("access_verified") is not True):
        raise ProfileError("documented_host_browser_permission_required")
    if origin(page["url"]) != allowed_origin:
        if not synthetic:
            raise ProfileError("application_origin_mismatch")
    if context.get("real_account_test") and context.get("full_state_restoration_verified") is not True:
        raise ProfileError("real_test_restoration_not_established")
    if context.get('real_account_test'):
        state=page.get('state_metadata',{})
        strategy=context.get('restoration_strategy',{})
        if strategy.get('kind')=='restore_uc_factual':
            from .uc_factual import contract
            spec=contract(page);validate_uc_state(state,page)
            current=next((i for s in state['sections'] for i in s['pages'] if i['href']==spec['path']),None)
            if (strategy.get('page_url')!=page['url'] or strategy.get('baseline_state_sha256')!=digest(state)
                    or not current or current['label']!=spec['review_label']
                    or next(s for s in state['sections'] if s['label']==spec['section'])['completion_text']!='Section Complete'):
                raise ProfileError('observed_uc_factual_restoration_evidence_required')
            return
        if strategy.get('kind')=='restore_uc_course_refill':
            validate_uc_state(state,page)
            route=page.get('uc_course_refill',{}).get('context',{}).get('summary_url')
            observed={i['href']:i['label'] for s in state['sections'] for i in s['pages']}
            if (not route or strategy.get('page_url')!=page['url'] or strategy.get('baseline_state_sha256')!=digest(state)
                    or strategy.get('baseline_parent_sha256') is None
                    or observed.get(urlsplit(route).path)!='Edit grade'
                    or observed.get('/my-application/acadHistAddInformation')!='Edit Additional information'
                    or next(s for s in state['sections'] if s['label']=='Academic history')['completion_text']!='Section Complete'):
                raise ProfileError('observed_uc_refill_restoration_evidence_required')
            return
        if strategy.get('kind')=='restore_uc_school_terms':
            validate_uc_state(state,page)
            required={'/my-application/acadhistFrHighSchool':'Edit High schools',
                      '/my-application/acadHistAddInformation':'Edit Additional information'}
            observed={i['href']:i['label'] for s in state['sections'] for i in s['pages']}
            if (page.get('uc_school_terms',{}).get('schema')!='uc-school-terms/1'
                    or strategy.get('page_url')!=page['url'] or strategy.get('baseline_state_sha256')!=digest(state)
                    or any(observed.get(key)!=label for key,label in required.items())
                    or next(s for s in state['sections'] if s['label']=='Academic history')['completion_text']!='Section Complete'):
                raise ProfileError('observed_uc_school_restoration_evidence_required')
            return
        if strategy.get('kind')=='restore_mit_coursework':
            if 'mit_coursework' not in page:
                raise ProfileError('observed_mit_restoration_evidence_required')
            validate_mit_coursework(page)
            validate_mit_state(state,page)
            if (strategy.get('page_url')!=page['url'] or strategy.get('baseline_state_sha256')!=digest(state)
                    or any(i['section']=='Self-reported coursework' for i in state['errors'])):
                raise ProfileError('observed_mit_restoration_evidence_required')
            return
        if strategy.get('kind') in {'restore_uc_personal','restore_uc_courses'}:
            validate_uc_state(state,page)
            courses=strategy['kind']=='restore_uc_courses'
            route=page.get('uc_course_editor',{}).get('summary_url','') if courses else page['url']
            current=next((i for s in state['sections'] for i in s['pages'] if 'https://apply.universityofcalifornia.edu'+i['href']==route),None)
            section='Academic history' if courses else 'About you'
            label='Edit grade' if courses else 'Edit Personal information'
            if (strategy.get('page_url')!=page['url'] or strategy.get('baseline_state_sha256')!=digest(state)
                    or courses != ('uc_course_editor' in page)
                    or (courses and strategy.get('baseline_parent_sha256')!=digest(page.get('uc_course_parent')))
                    or (courses and not any(i['href']=='/my-application/acadHistAddInformation' and i['label']=='Edit Additional information'
                        for s in state['sections'] for i in s['pages']))
                    or not current or current['label']!=label
                    or next(s for s in state['sections'] if s['label']==section)['completion_text']!='Section Complete'):
                raise ProfileError('observed_uc_restoration_evidence_required')
            return
        current=next((item for item in state.get('items',[]) if item['key']==state.get('current_page_key')),None)
        grade=strategy.get('kind')=='restore_completed_grade_dialog'
        strategy_known=(page.get('scope',{}).get('kind')=='common_app_grade_dialog'
            and page.get('editor_state',{}).get('schema')=='grade-parent/1'
            and page['editor_state']['completion_checked'] is True
            and strategy.get('baseline_parent_sha256')==digest(page['editor_state'])) if grade else strategy.get('kind')=='restore_completed_native_page'
        if ((origin(page['url'])!='https://apply.commonapp.org' and not synthetic)
                or state.get('schema')!='observed-state/1' or state.get('coverage')!='common_app_visible_navigation'
                or not current or current['status']!='complete'
                or not strategy_known
                or strategy.get('current_page_key')!=state['current_page_key']
                or strategy.get('baseline_state_sha256')!=digest(state)):
            raise ProfileError('observed_completed_page_restoration_evidence_required')

