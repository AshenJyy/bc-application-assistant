"""One observed Common App IELTS shape; answers stay in the canonical profile."""
import json
from importlib.resources import files
from urllib.parse import urlsplit

from .profile import ProfileError

CONTRACT=json.loads(files('bc_application').joinpath('data/common_ielts.json').read_text(encoding='utf-8'))


def exam(profile):
    matches=[e for e in profile['exams'].values() if e['system']=='IELTS' and e['name']=='IELTS Academic']
    return matches[0] if len(matches)==1 else None


def validate(page):
    tag=page.get('common_ielts',{});native=page.get('common_ielts_native',{})
    state=page.get('state_metadata',{})
    expected={f['key']:f for f in CONTRACT['fields']};fields={f['key']:f for f in page['fields']}
    if (urlsplit(page['url']).path!=CONTRACT['path'] or page['title']!=CONTRACT['title']
            or tag!={'schema':'common-ielts-page/1','content_sha256':CONTRACT['content_sha256']}
            or page.get('scope') or page.get('collections') or page.get('frames_present') or set(fields)!=set(expected)
            or native.get('schema')!='common-ielts-native/1' or native.get('heading')!='IELTS'
            or state.get('coverage')!='common_app_visible_navigation'
            or state.get('current_page_key')!='tertiaryNavItem2_10'
            or not {'secondaryNavItem2','tertiaryNavItem2_10'}<={i['key'] for i in state.get('items',[])}):
        raise ProfileError('observed_common_ielts_contract_required')
    if urlsplit(page['url']).netloc not in {'apply.commonapp.org','127.0.0.1:8765','localhost:8765'}:
        raise ProfileError('observed_common_ielts_origin_required')
    choice={k for k,f in expected.items() if f['control']=='choice_input'}
    dates={k for k,f in expected.items() if f['control']=='text'}
    for key,f in fields.items():
        if (any(f[k]!=expected[key][k] for k in ('label','group','control')) or not f['required']
                or f['disabled'] or f['readonly'] or not f.get('selector')
                or f.get('selector_count',1)!=1 or f.get('selector_index',0)!=0):
            raise ProfileError('observed_common_ielts_fields_required')
    controls=native.get('controls',[])
    if len(controls)!=len(choice) or {c['key'] for c in controls}!=choice or any(
            any(c.get(k)!=v for k,v in {'tag':'INPUT','type':'text','role':'combobox','popup':'listbox',
                                       'expanded':'false','wrapper':'NG-SELECT'}.items()) for c in controls):
        raise ProfileError('observed_common_ielts_choice_widgets_required')
    aux=native.get('auxiliary',[]);calendars=[a for a in aux if a.get('kind')=='calendar'];clears=[a for a in aux if a.get('kind')=='clear']
    if (len(aux)!=len(calendars)+len(clears) or len(calendars)!=len(dates)
            or {a.get('field_key') for a in calendars}!=dates or len({a.get('field_key') for a in clears})!=len(clears)
            or not {a.get('field_key') for a in clears}<=choice):
        raise ProfileError('observed_common_ielts_auxiliary_required')
    choices=page.get('choice_observations',{})
    if set(choices)!=choice:raise ProfileError('observed_common_ielts_choices_required')
    for options in choices.values():
        if (not isinstance(options,list) or not 1<=len(options)<=100
                or any(not isinstance(o.get('label'),str) or not o['label'] or o.get('value')!=o['label']
                       or type(o.get('disabled')) is not bool for o in options)
                or len({o['label'] for o in options})!=len(options)):
            raise ProfileError('observed_common_ielts_choices_required')
    actions=[a for a in page['actions'] if a['key']=='i:sectionContinue10' and a['label']=='Continue to next section'
             and a['selector']=='[id="sectionContinue10"]' and not a['disabled']]
    if len(actions)!=1:raise ProfileError('observed_common_ielts_draft_save_required')


def saved_state_matches(original,current):
    from .common_pages import state_matches
    return state_matches(original,current,'tertiaryNavItem2_10','secondaryNavItem2')


def resumable_state(original,current):
    from .common_pages import state_matches
    return state_matches(original,current,'tertiaryNavItem2_10','secondaryNavItem2',resume=True)


def resume(profile,checkpoint_id,page):
    from .common_pages import resume as resume_page
    if 'common_ielts' not in page:raise ProfileError('prepared_common_ielts_checkpoint_required')
    return resume_page(profile,checkpoint_id,page)
