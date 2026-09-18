import json
import pytest
from fastapi.testclient import TestClient
from catalyst import store, imports, closing, estimates
from catalyst.api import app

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    with TestClient(app) as c:
        yield c

def data():
    base={'part':'28957-2JDF0','customer':'현대 울산','date':'2026-08-01'}
    imports.commit_rows([{**base,**r} for r in [
        {'kind':'part'}, {'kind':'price','price':'1'},
        {'kind':'opening','quantity':'2265','amount':'2265'},
        {'kind':'receipt','quantity':'5222'}, {'kind':'settlement','quantity':'0'},
    ]],None,'test','append','test',True)

def payload(**kwargs):
    return {'period':'2026-08','part':'28957-2JDF0','customer':'현대 울산','price':'131518','reason':'확정 전 지출 추정',**kwargs}

def test_separate_estimate_snapshot_and_next_month(client):
    data()
    before=closing.preview('2026-08')
    assert client.post('/api/price-estimates',json=payload()).status_code==200
    p=closing.preview('2026-08'); r=p['details'][0]
    assert r['closing_amount']=='7487'
    assert r['estimated_closing_amount']=='984675266'
    assert r['settlement_amount']=='0'
    assert p['fingerprint']!=before['fingerprint']
    with pytest.raises(ValueError,match='변경'):closing.finalize('2026-08',before['fingerprint'])
    run=closing.finalize('2026-08',p['fingerprint'])
    estimates.save(payload(price='200000',reason='재추정'))
    with store.db() as c:
        frozen=json.loads(c.execute('SELECT snapshot FROM runs WHERE id=?',(run['id'],)).fetchone()[0])
    assert frozen['details'][0]['estimated_closing_amount']=='984675266'
    sep=closing.preview('2026-09')['details'][0]
    assert sep['opening_amount']=='7487'
    assert sep['estimated_price'] is None
    assert sep['estimated_closing_amount'] is None

@pytest.mark.parametrize('price',['NaN','Infinity','-Infinity','-1','bad',''])
def test_invalid_price(client,price):
    assert client.post('/api/price-estimates',json=payload(price=price)).status_code==422
    assert client.get('/api/price-estimates').json()==[]

def test_zero_disable_scope_and_audit(client):
    data()
    estimates.save(payload(customer='다른 거래처'))
    assert closing.preview('2026-08')['details'][0]['estimated_price'] is None
    estimates.save(payload(price='0'))
    assert closing.preview('2026-08')['details'][0]['estimated_closing_amount']=='0'
    estimates.save(payload(enabled=False,reason='추정 중단'))
    assert closing.preview('2026-08')['details'][0]['estimated_price'] is None
    with store.db() as c:
        assert c.execute("SELECT COUNT(*) FROM audit WHERE action='price_estimate'").fetchone()[0]==3
    assert client.post('/api/price-estimates',json=payload(reason='')).status_code==422
    assert client.post('/api/price-estimates',json=payload(period='2026-13')).status_code==422

def test_estimate_does_not_replace_actual_settlement_or_missing_price(client):
    data()
    base={'part':'28957-2JDF0','customer':'현대 울산','date':'2026-08-20'}
    imports.commit_rows([{**base,'kind':'settlement','quantity':'100'}],None,'additional','append','정산 테스트',True)
    estimates.save(payload())
    r=closing.preview('2026-08')['details'][0]
    assert r['settlement_amount']=='100'
    assert r['closing_amount']=='7387'
    assert r['estimated_closing_amount']==str(7387*131518)
    with store.db() as c:
        c.execute("DELETE FROM records WHERE kind='price'")
    p=closing.preview('2026-08')
    assert not p['ready']
    assert p['details'][0]['settlement_amount'] is None
    assert any(i['code']=='price' for i in p['issues'])
