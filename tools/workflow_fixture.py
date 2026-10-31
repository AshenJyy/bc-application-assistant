"""Connected fictional Education -> Courses fixture; no applicant file endpoints."""
from http.server import HTTPServer
from tools.synthetic_server import Handler
from tools.school_fixture import build as schools
from tools.academic_fixture import build as academic


if __name__=='__main__':
    Handler.pages={p:schools(academic_storage='bc-synthetic-connected-academic-v24',storage='bc-synthetic-connected-schools-v24') for p in ('/common/4/18','/common/4/19')}
    Handler.pages['/common/13/55']=academic(school_registry='bc-synthetic-connected-schools-v24',storage='bc-synthetic-connected-academic-v24')
    Handler.pages['/common/4/next']=b'<!doctype html><h1>Fictional draft saved</h1>'
    print('Connected invented school/academic UI at loopback port 8765',flush=True)
    HTTPServer(('127.0.0.1',8765),Handler).serve_forever()
