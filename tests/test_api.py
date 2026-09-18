import json
import pytest
from fastapi.testclient import TestClient
from catalyst import store, imports
from catalyst.api import app

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path)
    with TestClient(app) as c:yield c

def test_manual_revision_and_backup_restore(client):
    row={'kind':'price','part':'P','customer':'기아 화성','date':'2026-08-01','price':'10'}
    body={'rows':[row],'scope':'수동 단가','reason':'최초 입력'}
    assert client.post('/api/records',json=body).status_code==200
    saved=client.post('/api/backups',json={}).json()['file']
    record=client.get('/api/records').json()[0]
    response=client.post(f'/api/records/{record["id"]}/revise',json={'row':{**row,'price':'12'},'reason':'단가 정정'})
    assert response.status_code==200,response.text
    changed=client.get('/api/records').json()
    assert len(changed)==1 and changed[0]['price']=='12'
    assert json.loads(changed[0]['provenance'])['reason']=='단가 정정'
    assert client.post(f'/api/records/{record["id"]}/revise',json={'row':row,'reason':'오래된 화면'}).status_code==422
    assert client.post('/api/restore',json={'file':saved}).status_code==200
    assert client.get('/api/records').json()[0]['price']=='10'

def test_origin_protection_and_invalid_upload(client):
    assert client.post('/api/backups',json={},headers={'Origin':'https://unrelated.example'}).status_code==403
    assert client.post('/api/upload',files={'file':('bad.exe',b'bad')}).status_code==422
    assert client.get('/api/status').json()['app']=='catalyst-closing'

def test_fixed_date_profile_does_not_auto_apply(client):
    first=store.ROOT/'first.csv';first.write_text('품번,수량\nP,1\n',encoding='utf-8')
    sid=imports.register(first)['id']
    config={'sheet':'CSV','header_row':1,'kind':'receipt','scope':'입고','mode':'replace','columns':{'part':0,'quantity':1},'defaults':{'date':'2026-08-01','customer':'기아 화성'}}
    imports.apply(sid,config)
    second=store.ROOT/'second.csv';second.write_text('품번,수량\nP,2\n',encoding='utf-8')
    next_id=imports.register(second)['id']
    with store.db() as c:
        assert c.execute('SELECT status FROM sources WHERE id=?',(next_id,)).fetchone()[0]=='pending'

def test_recurring_profile_replaces_only_matching_month(client):
    config={'sheet':'CSV','header_row':1,'kind':'receipt','scope':'입고','mode':'replace','columns':{'part':0,'quantity':1,'date':2},'defaults':{'customer':'기아 화성'}}
    for name,q,day in [('aug',1,'2026-08-01'),('aug_fixed',2,'2026-08-01'),('sep',3,'2026-09-01')]:
        source=store.ROOT/(name+'.csv');source.write_text(f'품번,수량,일자\nP,{q},{day}\n',encoding='utf-8')
        sid=imports.register(source)['id']
        if name=='aug':imports.apply(sid,config)
    rows=client.get('/api/records').json()
    assert sorted((r['date'],r['quantity']) for r in rows)==[('2026-08-01','2'),('2026-09-01','3')]

def test_conflicting_prices_in_same_batch(client):
    base={'kind':'price','part':'P','date':'2026-08-01'}
    response=client.post('/api/records',json={'rows':[{**base,'price':'10'},{**base,'price':'12'}],'scope':'단가','reason':'시험'})
    assert response.status_code==422
    assert client.get('/api/records').json()==[]
