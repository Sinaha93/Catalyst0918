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

def test_output_delete_and_removed_restore(client):
    path=store.ROOT/'outputs'/'report.xlsx';path.write_bytes(b'test output')
    outside=store.ROOT/'keep.xlsx';outside.write_bytes(b'keep')
    assert client.post('/api/outputs/report.xlsx/delete',json={}).status_code==422
    assert path.exists()
    assert client.post('/api/outputs/report.xlsx/delete',json={'confirm':True}).status_code==200
    assert not path.exists() and outside.exists()
    assert client.get('/api/outputs').json()==[]
    assert client.post('/api/outputs/report.xlsx/delete',json={'confirm':True}).status_code==404
    assert client.post('/api/sources/1/cancel-or-restore',json={}).status_code==410

def test_source_delete_api_hides_list(client):
    path=store.ROOT/'sample.csv';path.write_text('a,b',encoding='utf-8')
    sid=imports.register(path)['id']
    preview=client.get(f'/api/sources/{sid}/impact').json()
    result=client.post(f'/api/sources/{sid}/delete',json={'fingerprint':preview['fingerprint'],'reason':'시험','confirm':True})
    assert result.status_code==200,result.text
    assert client.get('/api/sources').json()==[]
    assert client.get('/api/status').json()['sources']==0
    assert result.json()['deleted_files']==0
    assert client.get(f'/api/sources/{sid}/download').status_code==200
    assert path.exists()

def test_folder_scan_removed(client):
    assert client.post('/api/scan',json={}).status_code in (404,405)

def test_registration_reset_routes(client):
    path=store.ROOT/'reset.csv';path.write_text('a,b',encoding='utf-8')
    imports.register(path)
    p=client.get('/api/registration-reset/preview').json()
    assert len(p['sources'])==1
    assert client.post('/api/registration-reset',json={'fingerprint':p['fingerprint']}).status_code==422
    result=client.post('/api/registration-reset',json={'fingerprint':p['fingerprint'],'confirm_text':'초기화'})
    assert result.status_code==200 and result.json()['deleted_files']==0
    assert client.get('/api/sources').json()==[] and path.exists()

def test_advanced_rules_and_history_api(client):
    payload={'period':'2026-05','part':'28957-03CR0','customer':'현대 모비스','enabled':True,'reason':'확인','before':None}
    assert client.post('/api/advanced/rules',json=payload).status_code==200
    assert client.post('/api/advanced/rules',json=payload).status_code==422
    saved=client.get('/api/advanced/rules').json()[0]
    assert client.post('/api/advanced/rules',json={**payload,'before':saved,'enabled':False}).status_code==200
    history=client.get('/api/advanced/history').json()['items']
    assert history[0]['detail']['after']['enabled']==0
    assert client.get('/api/advanced/history?before='+str(history[-1]['id'])).json()['items']==[]
    assert client.post('/api/advanced/rules',json={**payload,'part':'28991-4C520'}).status_code==422

def test_history_filter_pagination_and_dates(client):
    path=store.ROOT/'search-target.csv';path.write_text('a,b',encoding='utf-8')
    sid=imports.register(path)['id']
    with store.db() as c:
        for i in range(25):
            c.execute('INSERT INTO audit(action,detail,created) VALUES(?,?,?)',('supplier_allocation',json.dumps({'source_id':sid,'part':'MATCH','reason':str(i)}),'2026-09-22T12:00:00+09:00'))
        store.audit(c,'unrelated',{'reason':'MATCH'})
    query='/api/advanced/history?action=supplier_allocation&query=search-target&since=2026-09-22&until=2026-09-22'
    first=client.get(query).json();second=client.get(query+'&before='+str(first['next'])).json()
    assert len(first['items'])==20 and len(second['items'])==5 and second['next'] is None
    assert not ({r['id'] for r in first['items']}&{r['id'] for r in second['items']})
    assert client.get(query.replace('search-target','absent')).json()['items']==[]
    assert client.get('/api/advanced/history?since=2026-09-23&until=2026-09-22').status_code==422
    assert client.get('/api/advanced/history?limit=0').status_code==422

def test_source_locations_and_legacy_missing_origin(client):
    from pathlib import Path
    path=store.ROOT/'input'/'location.csv';path.write_text('a,b',encoding='utf-8')
    sid=imports.register(path)['id']
    row=client.get('/api/sources').json()[0]
    assert row['registered_from']==str(path.resolve())
    assert row['registered_from_kind']=='input'
    assert Path(row['storage_path']).parent==(store.ROOT/'archive').resolve()
    assert row['storage_exists'] is True
    with store.db() as c:c.execute('UPDATE sources SET meta=? WHERE id=?',(json.dumps({'type':'legacy'}),sid))
    row=client.get('/api/sources').json()[0]
    assert row['registered_from'] is None and row['storage_exists'] is True

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
