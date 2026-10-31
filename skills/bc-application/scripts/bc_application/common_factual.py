"""Observed household and repeated language groups; no applicant-specific layout."""
import json
import re
from importlib.resources import files
from urllib.parse import urlsplit

from .profile import ProfileError

BASE='https://apply.commonapp.org'
CONTRACTS=json.loads(files('bc_application').joinpath('data/common_native_forms.json').read_text(encoding='utf-8'))


def contract(page):
    tag=page.get('common_factual',{})
    spec=next((s for s in CONTRACTS if s['kind']==tag.get('kind') and urlsplit(page['url']).path==s['path']),None)
    expected=spec.get('empty_content_sha256') if spec and spec['kind']=='language' and tag.get('rows')==[] else spec.get('content_sha256') if spec else None
    if (spec is None or tag.get('schema')!='common-factual-page/1'
            or tag.get('content_sha256')!=expected):
        raise ProfileError('observed_common_factual_contract_required')
    return spec


def field_specs(page):
    spec=contract(page)
    if spec['kind']!='language':return spec['fields']
    rows=page['common_factual'].get('rows',[])
    if not isinstance(rows,list) or not 0<=len(rows)<=5:raise ProfileError('observed_language_rows_required')
    used=set();result=[spec['count_field']]
    for index,row in enumerate(rows):
        if (set(row)!={'language_key','proficiency_id'} or not re.fullmatch(r'i:text_ques_\d+',row['language_key'])
                or not re.fullmatch(r'\d+',row['proficiency_id']) or row['language_key'] in used
                or row['proficiency_id'] in used):raise ProfileError('observed_language_rows_required')
        language_id=row['language_key'].removeprefix('i:text_ques_')
        if language_id in used or language_id==row['proficiency_id']:raise ProfileError('observed_language_rows_required')
        used.update((row['language_key'],language_id,row['proficiency_id']))
        result.append({'key':row['language_key'],'label':spec['language_label'],'group':'','control':'choice_input',
            'required':True,'language_index':index,'part':'label'})
        for item in spec['proficiencies']:
            result.append({'key':f'g:{row["proficiency_id"]}:{item["part"]}','label':item['label'],
                'group':spec['proficiency_label'],'control':'checkbox','required':False,'fact_required':True,
                'selector':f'fieldset:has([id="title_ques_{row["proficiency_id"]}"]) input[type="checkbox"][value="{item["value"]}"]',
                'language_index':index,'part':item['part']})
    return result


def validate(page):
    spec=contract(page);expected={s['key']:s for s in field_specs(page)};fields={f['key']:f for f in page['fields']}
    native=page.get('common_factual_native',{});state=page.get('state_metadata',{})
    if (urlsplit(page['url']).netloc not in {'apply.commonapp.org','localhost:8765','127.0.0.1:8765'}
            or page['title']!=spec['title'] or page.get('scope') or page.get('collections') or page.get('frames_present')
            or set(fields)!=set(expected) or native.get('schema')!='common-factual-native/1'
            or native.get('heading')!=spec['heading'] or state.get('coverage')!='common_app_visible_navigation'
            or state.get('current_page_key')!=spec['current_key']
            or not {spec['parent_key'],spec['current_key']}<={i['key'] for i in state.get('items',[])}):
        raise ProfileError('observed_common_factual_shape_required')
    for key,f in fields.items():
        wanted=expected[key]
        if (any(f[k]!=wanted[k] for k in ('label','group','control','required')) or f['disabled'] or f['readonly']
                or not f.get('selector') or f.get('selector_count',1)!=1 or f.get('selector_index',0)!=0
                or wanted.get('selector',f['selector'])!=f['selector']):
            raise ProfileError('observed_common_factual_fields_required')
    if spec['kind']=='grade12_status':
        field=fields[spec['fields'][0]['key']]
        selected=next((o['label'] for o in field['options'] if o['value']==field['value']),None)
        if field['value']!='' and selected!='No':raise ProfileError('grade12_official_grade_layout_not_supported')
    if spec['kind']=='language':
        count=fields[spec['count_field']['key']];options=count['options'];rows=len(page['common_factual']['rows'])
        selected=next((o['label'] for o in options if o['value']==count['value']),None)
        if ([o['label'] for o in options]!=[str(i) for i in range(1,6)] or len({o['value'] for o in options})!=5
                or any(o['disabled'] for o in options) or (count['value']=='' and rows)
                or (count['value']!='' and selected!=str(rows))):
            raise ProfileError('observed_language_count_rows_required')
    choices={s['key'] for s in expected.values() if s['control']=='choice_input'}
    widgets=native.get('controls',[])
    if (len(widgets)!=len(choices) or {w['key'] for w in widgets}!=choices or any(
            any(w.get(k)!=v for k,v in {'tag':'INPUT','type':'text','role':'combobox','popup':'listbox',
                'expanded':'false','wrapper':'NG-SELECT'}.items()) for w in widgets)):
        raise ProfileError('observed_common_factual_widgets_required')
    if set(page.get('choice_observations',{}))!=choices:raise ProfileError('observed_common_factual_choices_required')
    actions=[a for a in page['actions'] if a['key']=='i:sectionContinue'+spec['path'].split('/')[-1]
        and a['label']=='Continue to next section' and not a['disabled'] and a['selector']==f'[id="sectionContinue{spec["path"].split("/")[-1]}"]']
    if len(actions)!=1:raise ProfileError('observed_common_factual_draft_save_required')


def binding(profile,page,field_key):
    item=next((s for s in field_specs(page) if s['key']==field_key),None)
    if item is None:return None
    if 'fact' in item:return item['fact']
    order=profile['facts'].get('personal.languages.order',{}).get('value')
    if not isinstance(order,list) or item['language_index']>=len(order):return None
    identifier=order[item['language_index']]
    if not isinstance(identifier,str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}',identifier):return None
    return f'personal.languages.{identifier}.{item["part"]}'


def language_requirements(profile):
    spec=next(s for s in CONTRACTS if s['kind']=='language');facts=profile['facts'];refs=['personal.languages.order']
    order=facts.get('personal.languages.order',{}).get('value')
    if (not isinstance(order,list) or not 1<=len(order)<=5
            or any(not isinstance(i,str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}',i) for i in order)
            or len(set(order))!=len(order)):
        return refs,[{'reason':'explicit_language_list_required'}]
    blockers=[];labels=[]
    for identifier in order:
        prefix=f'personal.languages.{identifier}.';label=facts.get(prefix+'label',{}).get('value');labels.append(label)
        refs.extend([prefix+'label',*[prefix+s['part'] for s in spec['proficiencies']]])
        flags=[facts.get(prefix+s['part'],{}).get('value') for s in spec['proficiencies']]
        if any(type(v) is not bool for v in flags):blockers.append({'reason':'explicit_language_proficiency_flags_required','language_id':identifier})
        elif not any(flags):blockers.append({'reason':'required_language_proficiency_selection_missing','language_id':identifier})
    if any(not isinstance(s,str) or not s.strip() for s in labels) or len(set(labels))!=len(labels):
        blockers.append({'reason':'distinct_explicit_language_labels_required'})
    if 'Other' in labels:blockers.append({'reason':'common_other_language_branch_requires_observation'})
    return refs,blockers


def fact_blockers(profile,page):
    spec=contract(page);facts=profile['facts']
    if spec['kind']=='grade12_status':
        if 'education.common_app.grade12.has_official_grades' not in facts:return []
        return [] if facts.get('education.common_app.grade12.has_official_grades',{}).get('value') is False else [
            {'reason':'grade12_official_grade_branch_requires_evidence_and_observation'}]
    if spec['kind']=='household':
        return [] if facts.get('family.independence_statuses_apply',{}).get('value') is False else [
            {'reason':'common_household_independence_branch_requires_observation'}]
    _,blockers=language_requirements(profile)
    order=facts.get('personal.languages.order',{}).get('value')
    if not isinstance(order,list) or len(order)!=len(page['common_factual']['rows']):
        blockers.append({'reason':'explicit_language_list_matching_observed_rows_required'})
    return blockers
