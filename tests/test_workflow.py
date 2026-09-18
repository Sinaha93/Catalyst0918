import json
import pytest
from catalyst import store, imports, closing

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path)
    store.init()

def row(kind,**kwargs):
    return {'kind':kind,'part':'P-001','customer':'기아 화성','date':'2026-08-01',**kwargs}

def load(rows,scope='test',mode='append'):
    return imports.commit_rows(rows,None,scope,mode,'테스트',True)

def setup_month():
    load([row('part'),row('price',price='12.30'),row('opening',quantity='2',amount='24.60'),row('receipt',quantity='10'),row('settlement',quantity='7')])

def test_decimal_and_snapshot():
    setup_month()
    p=closing.preview('2026-08')
    assert p['ready'],p['issues']
    assert p['details'][0]['closing']=='5'
    assert p['details'][0]['closing_amount']=='61.50'
    result=closing.finalize('2026-08',p['fingerprint'])
    load([row('receipt',date='2026-09-01',quantity='4'),row('settlement',date='2026-09-01',quantity='2'),row('price',date='2026-09-01',price='20')])
    september=closing.preview('2026-09')
    assert september['details'][0]['opening']=='5'
    assert september['details'][0]['settlement_amount']=='40'
    with store.db() as c:
        frozen=json.loads(c.execute('SELECT snapshot FROM runs WHERE id=?',(result['id'],)).fetchone()[0])
        assert frozen.pop('report_context') is not None
        assert frozen==p

def test_missing_price_is_not_zero():
    load([row('part'),row('opening',quantity=0),row('receipt',quantity=1),row('settlement',quantity=1)])
    p=closing.preview('2026-08')
    assert not p['ready']
    assert p['details'][0]['settlement_amount'] is None
    with pytest.raises(ValueError): closing.finalize('2026-08',p['fingerprint'])

def test_replace_not_append_and_revision():
    setup_month()
    p=closing.preview('2026-08')
    closing.finalize('2026-08',p['fingerprint'])
    load([row('receipt',quantity=2)],'additional','replace')
    load([row('receipt',quantity=3)],'additional','replace')
    p2=closing.preview('2026-08')
    assert p2['details'][0]['receipt']=='13'
    assert closing.finalize('2026-08',p2['fingerprint'])['version']==2
    with pytest.raises(ValueError): closing.finalize('2026-08',p2['fingerprint'])

def test_failed_batch_is_atomic():
    with pytest.raises(ValueError): load([row('receipt',quantity=3),row('receipt',quantity='bad')])
    with store.db() as c: assert c.execute('SELECT COUNT(*) FROM records').fetchone()[0]==0

def test_price_conflict():
    load([row('price',price=10)])
    with pytest.raises(ValueError): load([row('price',price=11)])

def test_duplicate_file():
    p=store.ROOT/'a.csv'
    p.write_text('품번,수량\nP-001,10\n',encoding='utf-8')
    first=imports.register(p)
    second=imports.register(p)
    assert second['duplicate']
    assert first['id']==second['id']

def test_stale_preview_blocked():
    setup_month()
    p=closing.preview('2026-08')
    load([row('receipt',quantity=1)])
    with pytest.raises(ValueError,match='변경'): closing.finalize('2026-08',p['fingerprint'])

def test_mapping_and_repeated_import():
    p=store.ROOT/'a.csv'
    p.write_text('품번,수량,일자,거래처\nP-001,10,2026-08-01,기아 화성\n',encoding='utf-8')
    sid=imports.register(p)['id']
    config={'sheet':'CSV','header_row':1,'kind':'receipt','scope':'입고','mode':'replace','columns':{'part':0,'quantity':1,'date':2,'customer':3}}
    assert imports.apply(sid,config)['count']==1
    with pytest.raises(ValueError): imports.apply(sid,config)

def test_month_cutoff():
    setup_month()
    load([row('receipt',date='2026-09-01',quantity='999')])
    assert closing.preview('2026-08')['details'][0]['receipt']=='10'

def test_nonfinite_rejected():
    for value in ('NaN','Infinity','-Infinity'):
        with pytest.raises(ValueError): load([row('price',price=value)])
