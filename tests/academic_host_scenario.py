"""Send invented staged observations to the Node host-port regression suite."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/bc-application/scripts'))
from test_common_academic import scenario,page,transition,REF
from bc_application import common_academic as ca


def stages():
    p,t,ctx=scenario();current=page();key=ca.prepare(p,t,REF,current,ctx)['checkpoint_id'];result=[]
    for _ in range(40):
        plan=ca.advance(p,key,current)['plan'];after=transition(current,plan)
        result.append({'before':current,'after':after,'plan':plan,'context':{**ctx,'journal_persisted':True}})
        if plan['stage']=='fields':return result
        current=after
    raise RuntimeError('bounded_fixture_required')


if __name__=='__main__':print(json.dumps(stages(),ensure_ascii=False))
