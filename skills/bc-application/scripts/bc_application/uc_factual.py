"""Shared, observed UC native-page contracts; public metadata contains no answers."""
import json
from importlib.resources import files

from .profile import ProfileError

CONTRACTS=json.loads(files('bc_application').joinpath('data/uc_native_forms.json').read_text(encoding='utf-8'))
BASE='https://apply.universityofcalifornia.edu'


def contract(page):
    tag=page.get('uc_factual',{})
    result=next((c for c in CONTRACTS if BASE+c['path']==page['url'] and c['kind']==tag.get('kind')),None)
    if tag.get('schema')!='uc-factual-page/1' or result is None:raise ProfileError('observed_uc_factual_contract_required')
    return result


def validate_factual(page):
    spec=contract(page);fields={f['key']:f for f in page['fields']}
    if (page['title']!=spec['title'] or page.get('frames_present') or page.get('collections') or page.get('scope')
            or set(fields)!={f['key'] for f in spec['fields']}):
        raise ProfileError('observed_uc_factual_shape_required')
    for expected in spec['fields']:
        f=fields[expected['key']]
        if (any(f[k]!=expected[k] for k in ('label','group','control')) or f['disabled'] or f['readonly']
                or not f.get('selector') or f.get('selector_count',1)!=1 or f.get('selector_index',0)!=0):
            raise ProfileError('observed_uc_factual_fields_required')
    actions=[a for a in page['actions'] if a['key']=='i:save' and a['label']=='Save & continue' and not a['disabled']]
    if len(actions)!=1 or actions[0]['selector']!='[id="save"]':raise ProfileError('observed_uc_factual_draft_save_required')
