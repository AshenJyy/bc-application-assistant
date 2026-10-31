"""Unregistered, loopback native forms with different vocabulary/order and fresh IDs."""
import json
from http.server import HTTPServer
from uuid import uuid4
from pathlib import Path

from tools.synthetic_server import Handler


def build(variant=0):
    script=r'''
const variant=VARIANT,prefix='PREFIX',key='bc-generic-demo-v26-'+variant;
const saved=JSON.parse(localStorage.getItem(key)||'null'),draft=saved?.values||{};
const labels=variant?{given:'Official first name',family:'Official surname',country:'Country of residence',birth:'Birth date',address:'Home street address',former:'Do any application records show a previous legal name?',former_name:'Name appearing on those earlier records',course:'Course title on PSR',mark:'Original school percentage',credits:'Original credits'}:
{given:'Given names on legal documents',family:'Family name on legal documents',country:'Where do you currently live?',birth:'Date of birth',address:'Permanent street',former:'Do any records use a former legal name?',former_name:'Former name shown on records',course:'Name of course',mark:'School mark (%)',credits:'Credits printed on PSR'};
const node=(tag,attrs={},text='')=>{const e=document.createElement(tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);e.textContent=text;return e;};
function input(parent,part,tag='input',type='text'){
 const id=prefix+'_'+part,e=node(tag,{id,name:id,required:'',...(tag==='input'?{type}:{})});e.value=draft[part]||'';
 e.oninput=()=>draft[part]=e.value;parent.append(node('label',{for:id},labels[part]),e);
}
function render(){const form=document.querySelector('form');form.replaceChildren(node('h2',{},variant?'Applicant record':'Applicant details'));
 form.id=prefix+'_form';form.append(node('p',{},'Enter factual details and original PSR values. Keep school marks and credits unchanged.'));
 const basics=node('fieldset');basics.append(node('legend',{},'Applicant basics'));input(basics,'given');input(basics,'family');
 const select=node('select',{id:prefix+'_country',name:prefix+'_country',required:''});
 for(const[i,label]of ['Choose country','Canada','China'].entries()){const o=node('option',{value:i?prefix+'_country_'+i:''},label);o.selected=draft.country===label;select.append(o);}
 select.onchange=()=>draft.country=select.selectedOptions[0].textContent;basics.append(node('label',{for:select.id},labels.country),select);
 input(basics,'birth','input','date');input(basics,'address','textarea');
 const prior=node('fieldset');prior.append(node('legend',{},labels.former));
 for(const[i,label]of ['Yes','No'].entries()){const id=prefix+'_prior_'+i,e=node('input',{id,type:'radio',name:prefix+'_prior',value:prefix+'_value_'+i,required:''});e.checked=draft.former===label;
 e.onchange=()=>{draft.former=label;render();};prior.append(e,node('label',{for:id},label));}
 if(draft.former==='Yes')input(prior,'former_name');
 const academic=node('fieldset');academic.append(node('legend',{},'Course 1'));input(academic,'course','textarea');input(academic,'mark');input(academic,'credits');
 for(const block of variant?[academic,prior,basics]:[basics,prior,academic])form.append(block);
 form.append(node('button',{id:prefix+'_save',type:'submit'},variant?'Save changes':'Save draft'));
 document.getElementById('status').textContent=saved?'Saved draft loaded':'Draft has not been saved';}
document.querySelector('form').onsubmit=e=>{e.preventDefault();localStorage.setItem(key,JSON.stringify({values:draft}));document.getElementById('status').textContent='Draft saved';};render();
'''.replace('VARIANT',str(variant)).replace('PREFIX',uuid4().hex[:12])
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Invented university application draft</title>'
        '<style>body{font:17px system-ui;background:#edf3fa;color:#183354;margin:24px auto;max-width:760px}header{padding:16px;background:#173a65;color:white;border-radius:8px}form{background:white;padding:20px;margin-top:14px;border-radius:8px}fieldset{margin:14px 0;border:1px solid #a9bdd4;padding:14px}label{display:block;margin:9px 0 4px}input,textarea,select,button{font:inherit;padding:6px}input:not([type=radio]),textarea,select{box-sizing:border-box;width:100%}input[type=radio]+label{display:inline-block;margin:8px 15px 8px 3px}textarea{height:38px}button{background:#245d99;color:white;border:0;padding:10px 22px}output{display:block;padding:12px}</style>'
        '<header><strong>Generic application demonstration</strong><div>Invented student and university — development test</div></header>'
        '<main><form method="post"></form><output id="status" role="status"></output></main><script>'+script+'</script></html>').encode()


class GenericHandler(Handler):
    def do_GET(self):
        if self.path in {'/widgets','/parent-records'}:
            fixture='generic_widgets.html' if self.path=='/widgets' else 'generic_parent_records.html'
            data=(Path(__file__).resolve().parents[1]/'tests/fixtures'/fixture).read_bytes()
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data);return
        if self.path not in {'/fresh-intake','/records'}:self.send_error(404);return
        data=build(0 if self.path=='/fresh-intake' else 1)
        self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)


if __name__=='__main__':
    print('Unregistered invented native forms on loopback port 8765',flush=True)
    HTTPServer(('127.0.0.1',8765),GenericHandler).serve_forever()
