import copy
import json
import pytest
from catalyst import plan_import as pi,imports,store,source_roles

def data():
    return {'계획':[pi.HEADERS,['2026-05-01','28957-2JDF0','현대 울산',2,1,2,'가단가'],['2026-05-01','28533-07010','현대 위아',0,25,0,'']]}

def test_plan_dates_money_zero_and_role():
    p=pi.parse(data(),{'source_id':1})
    assert (p['period'],p['count'],p['quantity'],p['amount'])==('2026-05',2,'2','2')
    assert all(r['kind']=='plan' for r in p['rows'])
    assert 'plan' in source_roles.describe({'type':pi.TYPE},[])['roles']
    assert not pi.matches({'입고':data()['계획']})

@pytest.mark.parametrize('row,col,value',[(1,3,None),(1,3,-1),(1,3,1.5),(1,4,None),(1,5,99),(1,2,'unknown'),(2,0,'2026-06-01'),(1,0,'bad')])
def test_invalid_plan_does_not_silently_import(row,col,value):
    d=data();d['계획'][row][col]=value
    with pytest.raises(ValueError):pi.parse(d,{})

@pytest.fixture
def root(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path);store.init()
    monkeypatch.setattr(imports,'tables',lambda p:data())
    return tmp_path

def test_auto_new_month_and_duplicate_protection(root):
    path=root/'renamed.csv';path.write_text('one',encoding='utf-8')
    sid=imports.register(path)['id']
    with store.db() as c:
        assert c.execute('SELECT status FROM sources WHERE id=?',(sid,)).fetchone()[0]=='imported'
        assert c.execute('SELECT COUNT(*) FROM records').fetchone()[0]==2
        assert c.execute("SELECT COUNT(*) FROM records WHERE kind='price'").fetchone()[0]==0
    assert imports.register(path)['duplicate']
    assert pi.preview(sid)['errors']
    with pytest.raises(ValueError,match='월계획'):imports.mapped_rows(sid,{})

def test_revision_needs_confirmation_and_keeps_other_month(root):
    one=root/'one.csv';one.write_text('one',encoding='utf-8');imports.register(one)
    imports.commit_rows([{'kind':'plan','date':'2026-04-01','part':'OTHER','customer':'현대 아산','quantity':'1'}],None,'april','append')
    two=root/'two.csv';two.write_text('two',encoding='utf-8');sid=imports.register(two)['id']
    p=pi.preview(sid);assert p['replace_count']==2 and not p['errors']
    with store.db() as c:assert c.execute('SELECT status FROM sources WHERE id=?',(sid,)).fetchone()[0]=='pending'
    with pytest.raises(ValueError):pi.apply(sid,{'fingerprint':'stale'})
    pi.apply(sid,{'fingerprint':p['fingerprint']})
    with store.db() as c:
        assert c.execute('SELECT count(*) FROM records r JOIN batches b ON b.id=r.batch_id WHERE b.active=1').fetchone()[0]==3

def test_manual_plan_collision_and_legacy_source_classification(root):
    imports.commit_rows([{'kind':'plan','date':'2026-05-01','part':'OTHER','customer':'현대 아산','quantity':'1'}],None,'manual','append')
    path=root/'renamed.csv';path.write_text('one',encoding='utf-8');sid=imports.register(path)['id']
    p=pi.preview(sid);assert p['errors']
    with pytest.raises(ValueError):pi.apply(sid,{'fingerprint':p['fingerprint']})
    from fastapi.testclient import TestClient
    from catalyst.api import app
    with store.db() as c:
        meta=json.loads(c.execute('SELECT meta FROM sources WHERE id=?',(sid,)).fetchone()[0]);meta['type']='열 연결 필요'
        c.execute('UPDATE sources SET meta=? WHERE id=?',(store.encode(meta),sid))
    client=TestClient(app)
    assert client.get('/api/sources').json()[0]['meta']['type']==pi.TYPE
    assert client.post(f'/api/sources/{sid}/plan-preview').json()['period']=='2026-05'
