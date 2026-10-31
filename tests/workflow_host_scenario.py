"""Invented end-to-end coordinator data/DOM transitions for the host regression."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/bc-application/scripts'))
from test_workflow import scenario
from test_common_schools import page as school_page,transition as school_transition,lookup
from test_common_academic import page as academic_page,transition as academic_transition
from bc_application.common_academic import layout
from bc_application.browser import values


def transition(data):
    page=data['page'];plan=data['plan'];saved=data.get('saved',False)
    if 'common_school' in page:return school_transition(page,plan,saved=saved)
    page=academic_transition(page,plan)
    if saved:
        config=[{'headers':{k:f['value'] for k,f in g['headers'].items()},'rows':len(g['rows'])} for g in layout(page).values()]
        page=academic_page(config,values(page),saved=True)
    return page


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='init':
        from bc_application.store import ProfileStore,ProfileSnapshot
        p,t,steps,routes,ctx=scenario();p.pop('school_directory')
        if len(sys.argv)>3:del p['facts']['education.boarding']
        ProfileStore(Path(sys.argv[2])).save(ProfileSnapshot(p,None));result={'created':True}
    elif len(sys.argv)>1:result=transition(json.load(sys.stdin))
    else:
        p,t,steps,routes,ctx=scenario();p.pop('school_directory')
        result={'profile':p,'target':t,'steps':steps,'routes':routes,'context':{**ctx,'workflow_authorized':True},
            'pages':{steps[0]['page_url']:school_page(),steps[1]['page_url']:school_page('other'),steps[2]['page_url']:academic_page()},
            'lookups':{'Fictional Secondary '+str(n):lookup('9999000'+str(n)) for n in (1,2)}}
    print(json.dumps(result,ensure_ascii=False))
