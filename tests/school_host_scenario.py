"""Invented source-backed school observations for the host regression suite."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/bc-application/scripts'))
from test_common_schools import scenario,page,transition,lookup
from bc_application import common_schools as ca


def stages(kind='current'):
    p,t,ref,ctx=scenario(kind,early=kind=='current');current=page(kind);key=ca.prepare(p,t,ref,current,ctx)['checkpoint_id'];result=[]
    for _ in range(15):
        plan=ca.advance(p,key,current)['plan'];after=transition(current,plan);saved=transition(current,plan,saved=True)
        result.append({'before':current,'after':after,'saved':saved,'plan':plan,'context':{**ctx,'journal_persisted':True},
            'lookup':lookup('99990002' if kind=='current' else '99990001',other=kind=='other')})
        if plan['stage']=='fields':return result
        current=after
    raise RuntimeError('bounded_school_fixture_required')


if __name__=='__main__':print(json.dumps(stages()+stages('other'),ensure_ascii=False))
