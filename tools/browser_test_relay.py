"""One-profile synthetic host relay; no browser connection or applicant files."""
import argparse
import json
from pathlib import Path

from bc_application.pages import build_plan,prepare,verify_saved,restoration_writes
from bc_application.profile import add_statement,bind_fact,bind_record_column,set_fact
from bc_application.store import ProfileStore

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'work/synthetic-browser'
CONTEXT={'transport':'extension','origin':'http://127.0.0.1:8765',
    'access_verified':True,'synthetic_test':True,'journal_persisted':True}


def relay(stage,system='common_app',page_kind='grades',browser_family='edge'):
    store=ProfileStore(FOLDER/'applicant.json'); snapshot=store.load()
    psr=snapshot.data['sources'][snapshot.data['psr_source_id']]
    if Path(psr['path']).resolve()!= (ROOT/'tests/fixtures/synthetic_psr.pdf').resolve():
        raise RuntimeError('Synthetic profile required; never operates on a real applicant')
    observed=json.loads((FOLDER/'relay.json').read_text(encoding='utf-8'))
    page=observed['page']
    routes={('uc','personal'):'/index.html',('mit','personal'):'/mit.html',
        ('common_app','personal'):'/common/3/11',('common_app','grades'):'/common/13/55',
        ('uc','controls'):'/uc_controls.html',('mit','coursework'):'/mit_coursework.html',
        ('uc','course_controls'):'/uc_course_controls.html'}
    expected=routes.get((system,page_kind))
    if not expected or page['url']!='http://127.0.0.1:8765'+expected or not page['title'].startswith('Synthetic '):
        raise RuntimeError('Invented loopback page required')
    if stage=='prepare':
        target=next(key for key,t in snapshot.data['targets'].items() if t['system']==system)
        if (system=='common_app' and page_kind=='personal' and
                'personal.has_materials_under_former_legal_name' not in snapshot.data['facts']):
            source=add_statement(snapshot.data,'Invented applicant explicitly reports no materials under a former legal name.')
            set_fact(snapshot.data,'personal.has_materials_under_former_legal_name',False,source)
        if page_kind=='grades':
            for index,code in enumerate(('MTEST10---','MSPLT10---','MWRAP11---')):
                record=next(c for c in snapshot.data['academic']['courses'] if c['raw_cells']['course_code']==code)
                bind_record_column(snapshot.data,target,f'i:repeatedGrade@{index}',record['record_id'],'school_percent',page_path=expected)
        if page_kind in {'coursework','course_controls'}:
            facts=({'education.subjects.calculus.status':'taken','education.subjects.physics.status':'in_progress_or_planned',
                'education.subjects.biology.status':'will_not_take','education.subjects.chemistry.status':'taken'}
                if page_kind=='coursework' else {'education.synthetic.category':'math-cs','education.synthetic.honor':'NH',
                    'education.synthetic.scale':'0-100 (Canada - BC)'})
            missing={key:value for key,value in facts.items() if key not in snapshot.data['facts']}
            if missing:
                source=add_statement(snapshot.data,'Invented student explicitly supplies test answers: '+json.dumps(missing))
                for key,value in missing.items(): set_fact(snapshot.data,key,value,source)
            if page_kind=='course_controls':
                for key,ref in {'subject':'education.synthetic.category','honor':'education.synthetic.honor','scale':'education.synthetic.scale'}.items():
                    bind_fact(snapshot.data,target,f'i:{key}',ref)
                record=next(c for c in snapshot.data['academic']['courses'] if c['raw_cells']['course_code']=='MTEST10---')
                bind_record_column(snapshot.data,target,'i:courseName',record['record_id'],'course_description')
                bind_record_column(snapshot.data,target,'i:grade',record['record_id'],'school_percent')
        plan=build_plan(snapshot.data,target,page)
        if not plan['ready']: raise RuntimeError('Synthetic grade plan blocked')
        store.save(snapshot)
        plan=prepare(snapshot.data,plan['checkpoint_id'],page,
            {**CONTEXT,'browser_family':browser_family})
        store.save(snapshot)
        (FOLDER/'plan.json').write_text(json.dumps(plan,indent=2)+'\n',encoding='utf-8')
        return {'ready':True,'writes':len(plan['writes']),'journal_persisted':True}
    plan=json.loads((FOLDER/'plan.json').read_text(encoding='utf-8'))
    if stage=='restore':
        result={'writes':restoration_writes(snapshot.data,plan['checkpoint_id'],page)}
        (FOLDER/'restore.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        return {'restoration_writes':len(result['writes'])}
    result=verify_saved(snapshot.data,plan['checkpoint_id'],page,
        revisited_after_save=observed.get('revisited_after_save') is True,restoration=stage=='verify-restored')
    store.save(snapshot)
    if not result['verified']: raise RuntimeError('Synthetic saved-state verification failed')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['prepare','verify','restore','verify-restored'])
    parser.add_argument('--system',choices=['uc','mit','common_app'],default='common_app')
    parser.add_argument('--page',choices=['personal','grades','controls','coursework','course_controls'],default='grades')
    parser.add_argument('--browser',choices=['chrome','edge'],default='edge')
    args=parser.parse_args()
    print(json.dumps(relay(args.stage,args.system,args.page,args.browser)))
