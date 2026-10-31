"""Loopback-only invented browser fixtures, never applicant files or a proxy."""
from http.server import BaseHTTPRequestHandler,HTTPServer
import html
from pathlib import Path

from tools.browser_fixture import build
from bc_application.adapters.mit import COURSEWORK_NOTES


STYLE='<style>body{max-width:780px;margin:24px auto;font:18px system-ui;color:#182b48}fieldset{margin:14px 0;padding:14px}label{display:block}textarea,input,button{font:inherit}textarea{height:35px}button{padding:12px 24px}</style>'
SCRIPT='''<script>
const form=document.querySelector('form'), storageKey=document.title;
const previous=JSON.parse(localStorage.getItem(storageKey)||'null');
if(previous)for(const e of form.elements){if(!e.name)continue;if(e.type==='radio')e.checked=e.value===previous[e.name];else e.value=previous[e.name]??'';}
form.addEventListener('submit',e=>{e.preventDefault();const result={};for(const el of form.elements){if(!el.name)continue;if(el.type!=='radio'||el.checked)result[el.name]=el.value;}
localStorage.setItem(storageKey,JSON.stringify(result));document.getElementById('status').textContent='Draft saved';});
</script>'''
MIT='''<fieldset><legend>Personal information</legend><label for="mitFirst">Legal First (Given)*</label><input id="mitFirst" name="first" value="Baseline" required>
<label for="mitLast">Legal Last (Family)*</label><input id="mitLast" name="last" value="Applicant" required></fieldset>
<fieldset><legend>Permanent address*</legend><label for="mitStreet">Street</label><textarea id="mitStreet" name="street" required>100 Synthetic Road</textarea></fieldset>
<button id="mitSave" type="submit">Save and Continue</button>'''
COMMON='''<fieldset><legend>Personal information</legend><label for="commonFirst">First name *</label><textarea id="commonFirst" name="first" required>Baseline</textarea>
<label for="commonLast">Last name *</label><textarea id="commonLast" name="last" required>Applicant</textarea>
<label for="commonBirth">Date of birth *</label><input id="commonBirth" name="birth" value="April 1, 2006" required></fieldset>
<fieldset><legend>Do you have any materials under a former legal name? *</legend><label for="formerNo">No</label><input id="formerNo" name="former" type="radio" value="no" checked required>
<label for="formerYes">Yes</label><input id="formerYes" name="former" type="radio" value="yes" required></fieldset>
<button id="sectionContinue11" type="submit">Continue to next section</button>'''
GRADES='''<fieldset><legend>Native grade controls with intentionally repeated IDs</legend>
<label for="repeatedGrade">Grade *</label>
<input id="repeatedGrade" name="grade_1" aria-label="Course 1 school percentage *" value="74" required>
<input id="repeatedGrade" name="grade_2" aria-label="Course 2 school percentage *" value="75" required>
<input id="repeatedGrade" name="grade_3" aria-label="Course 3 school percentage *" value="76" required>
</fieldset><button id="sectionContinue55" type="submit">Continue to next section</button>'''

UC_COURSE='''<fieldset><legend>Invented course row</legend>
<div class="field-wrapper"><label for="staleSubject">Subject Area/Course Category</label><div><select id="subject" name="subject" required>
<optgroup label="Mathematics"><option value="math-cs">Computer Science</option></optgroup>
<optgroup label="Science"><option value="science-cs" selected>Computer Science</option></optgroup></select></div></div>
<div class="field-wrapper"><label for="courseName">Course Name</label><input id="courseName" name="courseName" value="Invented baseline course" required></div>
<div class="field-wrapper"><label for="honor">Honor Type</label><select id="honor" name="honor" required><option value="NH">NH</option><option value="AP" selected>AP</option></select></div>
<div class="field-wrapper"><label for="staleScale">Grading System</label><div><select id="scale" name="scale" required><option value="BC">0-100 (Canada - BC)</option><option value="OTHER" selected>Other</option></select></div></div>
<label for="grade">Grade 1</label><select id="grade" name="grade" required><option>74</option><option>84</option></select>
</fieldset><div style="visibility:hidden"><label for="hiddenNote">Essay *</label><textarea id="hiddenNote" name="hiddenNote"></textarea></div>
<button id="save" type="submit">Save &amp; continue</button>'''


def coursework():
    fields=['<label for="standardizedNote">'+html.escape(COURSEWORK_NOTES[0])+'</label><textarea id="standardizedNote" name="standardizedNote"></textarea>']
    for subject in ('calculus','physics','biology','chemistry'):
        fields.append(f'<fieldset><legend>{subject.title()}*</legend><label for="{subject}">{subject.title()}*</label>'
            f'<select id="{subject}" name="{subject}" required><option value="taken">Taken</option>'
            '<option value="planned">In progress/will take</option><option value="not-planned">Will not take</option></select></fieldset>'
            f'<fieldset><legend>Year</legend><label for="{subject}Year">Year</label><select id="{subject}Year" name="{subject}Year"><option>9th</option><option>10th</option><option>11th</option><option>12th</option></select></fieldset>')
    fields.append('<label for="contextNote">'+html.escape(COURSEWORK_NOTES[1])+'</label><textarea id="contextNote" name="contextNote"></textarea><button type="submit">Save and Continue</button>')
    return ''.join(fields)


def mock(title,fields):
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><title>'+title+'</title>'+STYLE+
        '<h1>'+title+'</h1><p>Development test only. All values are invented; this is not an application account.</p><form>'+
        fields+'</form><p role="status" id="status"></p>'+SCRIPT+'</html>').encode()


class Handler(BaseHTTPRequestHandler):
    pages={}
    def do_GET(self):
        if self.path not in self.pages:
            self.send_error(404); return
        data=self.pages[self.path]
        self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(data)
    def log_message(self,*args): pass


if __name__=='__main__':
    folder=build()
    build(alternate=True)
    Handler.pages={'/index.html':(folder/'index.html').read_bytes(), '/mit.html':mock('Synthetic MIT personal information',MIT),
        '/common/3/11':mock('Synthetic Common App personal information',COMMON),
        '/common/13/55':mock('Synthetic Common App native grade controls',GRADES),
        '/mit_coursework.html':mock('Synthetic MIT self-reported coursework',coursework()),
        '/uc_course_controls.html':mock('Synthetic UC course labels',UC_COURSE),
        '/uc_controls.html':(folder/'uc_controls.html').read_bytes()}
    print('Synthetic fixtures listening on loopback port 8765',flush=True)
    HTTPServer(('127.0.0.1',8765),Handler).serve_forever()
