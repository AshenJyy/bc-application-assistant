"""Initialize one disposable synthetic profile for the documented Edge/Chrome bridge."""
from pathlib import Path

from bc_application.profile import create_profile,add_statement,add_target,set_fact
from bc_application.store import ProfileStore,ProfileSnapshot

ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/'work/synthetic-browser'
folder.mkdir(parents=True,exist_ok=True)
store=ProfileStore(folder/'applicant.json')
if store.path.exists(): raise SystemExit('Use the existing synthetic profile; refuses overwrite')
data=create_profile(ROOT/'tests/fixtures/synthetic_psr.pdf')
source=add_statement(data,'Invented student explicitly confirms these factual values for a disposable browser test only.')
facts={'personal.legal_given_name':'Synthetic','personal.legal_family_name':'Applicant',
       'personal.has_lived_name':False,'personal.has_previous_legal_name':False,
       'personal.birth_month':'March','personal.birth_day':'05','personal.birth_year':'2007',
       'personal.birth_country':'Canada','personal.birth_city':'Victoria',
       'education.attended_california_public_school':False}
for key,value in facts.items(): set_fact(data,key,value,source)
target=add_target(data,system='uc',school='Synthetic UC campus',program=None,source_id=source)
store.save(ProfileSnapshot(data,None))
print(target)
