"""Generate a public, invented UC-layout page for supported host-browser tests."""
import html
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def build(*, alternate=False):
    page=json.loads((ROOT/'tests/fixtures/uc_personal_page.json').read_text(encoding='utf-8'))
    defaults={'firstName':'Baseline','lastName':'Applicant','middleName':'','suffixName':'',
              'hasLivedName':'N','otherNames':'no','birthDateMM':'03','birthDateDD':'05',
              'birthDateYYYY':'2007','birthCountryCode':'260','birthCity':'Vancouver','hasAttendedCaPublicSchool':'N'}
    if alternate:
        defaults.update(hasLivedName='Y',otherNames='yes',birthDateMM='04',birthDateDD='01',
            birthDateYYYY='2006',birthCountryCode='273',hasAttendedCaPublicSchool='Y')
    fields=[]
    esc=html.escape
    for f in page['fields']:
        name=f['name']; control=f['control']; required=' required' if f['required'] else ''
        if control=='radio':
            controls=[]
            for o in f['options']:
                # The fixture models required radio questions explicitly.
                control_id=o['selector'].split('"')[1]
                checked=' checked' if defaults[name]==o['value'] else ''
                controls.append(f'<input id="{esc(control_id)}" name="{esc(name)}" type="radio" value="{esc(o["value"])}"{checked} required><label for="{esc(control_id)}">{esc(o["label"])}</label>')
            fields.append(f'<fieldset><legend>{esc(f["group"])}</legend>{" ".join(controls)}</fieldset>')
        else:
            control_id=f['selector'].split('"')[1]
            label=f'<label for="{esc(control_id)}">{esc(f["label"])}</label>'
            if control=='select':
                options=''.join(f'<option value="{esc(o["value"])}"'+(' selected' if defaults[name]==o['value'] else '')+f'>{esc(o["label"])}</option>' for o in f['options'])
                field=f'<select id="{esc(control_id)}" name="{esc(name)}"{required}>{options}</select>'
            else:
                field=f'<input id="{esc(control_id)}" name="{esc(name)}" type="{control}" value="{esc(defaults[name])}"{required}>'
            fields.append(f'<fieldset><legend>{esc(f["group"])}</legend>{label} {field}</fieldset>')
    output=ROOT/'work/synthetic-browser/site'
    output.mkdir(parents=True,exist_ok=True)
    body='''<!doctype html><html lang="en"><meta charset="utf-8"><title>Synthetic UC page</title>
<style>body{max-width:780px;margin:24px auto;font:17px system-ui;color:#182b48}fieldset{margin:12px 0;padding:10px;border:1px solid #c4cedd}legend{font-weight:600}input,select{font:inherit}button{font:inherit;padding:12px 24px;background:#16437b;color:white}aside{padding:12px;background:#eaf3ff}</style>
<h1>Synthetic UC personal information</h1><aside>Development test only. All values are invented. This is not an application account.</aside>
<form id="form">'''+''.join(fields)+'''<button id="save" type="submit">Save &amp; continue</button></form><p id="status" role="status"></p>
<script>
const form=document.getElementById('form');
function state(){const result={};for(const e of form.elements){if(!e.name)continue;if(e.type==='radio'){if(e.checked)result[e.name]=e.value;}else result[e.name]=e.value;}return result;}
function load(){const saved=JSON.parse(localStorage.getItem('bc-synthetic-uc')||'null');if(!saved)return;for(const e of form.elements){if(!e.name)continue;if(e.type==='radio')e.checked=e.value===saved[e.name];else e.value=saved[e.name]??'';}document.getElementById('status').textContent='Saved draft loaded';}
form.addEventListener('submit',e=>{e.preventDefault();localStorage.setItem('bc-synthetic-uc',JSON.stringify(state()));document.getElementById('status').textContent='Draft saved';});load();
</script></html>'''
    if alternate:
        body=body.replace('<title>Synthetic UC page</title>','<title>Synthetic UC alternate controls</title>')
        body=body.replace('bc-synthetic-uc','bc-synthetic-uc-controls')
    (output/('uc_controls.html' if alternate else 'index.html')).write_text(body,encoding='utf-8')
    return output


if __name__=='__main__': print(build())
