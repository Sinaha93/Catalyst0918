import copy
import json
from pathlib import Path
import pytest
from catalyst import supplier_import as si, imports, store, source_lifecycle


def umicore():
    return {'납품 Summary':[
        ['제목'],
        ['NO','품 번','전월적송재고','Total 납품','1주','당월마감수량','','당월적송수량'],
        [None,None,None,None,None,'1차','Total',None],
        [1,'28991-4C520',2,10,10,None,9,3],
        ['Total',None,2,10,10,None,9,3],
        [None,None,None,None,None,None,None,'#VALUE!'],
    ]}

def heesung():
    return {'5월 마감':[
        [None,2,10,9,9,12,3],
        ['품번','적송(이월)','출하','모비스','계','적송+출하','차이'],
        ['28957-03CR0',2,10,9,9,12,3],
        [None,None,None,0,0,0,0],
    ]}


def test_auto_columns_and_reference_values():
    u=si.parse(umicore(),'2026-05')
    assert u['totals']=={'opening':'2','delivery':'10','settlement':'9','closing':'3'}
    assert u['items'][0]['counterparty']=='전주공장'
    h=si.parse(heesung(),'2026-05')
    assert h['totals']['delivery']=='10' # NOT the 9 in 계 or 12 in 적송+출하
    assert si.identify(umicore())==si.TYPES['umicore']
    with pytest.raises(ValueError,match='마감 월'):si.parse(umicore(),'')
    with pytest.raises(ValueError,match='시트는'):si.parse(heesung(),'2026-08')
    duplicate=heesung();duplicate['Sheet1']=copy.deepcopy(duplicate['5월 마감'])
    assert si.parse(duplicate,'2026-05')['parts']==1


def test_remark_grammar_is_strict():
    assert si.remark_allocation('50개 글로비스+350개 전주')=={'현대 글로비스':'50','현대 전주':'350'}
    for note in ('개발품','50개 글로비스+미확인','50개 글로비스 추가 예정','1원 가단가',''):
        assert si.remark_allocation(note) is None


@pytest.mark.parametrize('row,col,value',[(3,3,11),(4,3,11),(3,1,'bad part'),(3,3,'#VALUE!')])
def test_invalid_totals_rows_and_cells_rejected(row,col,value):
    data=umicore();data['납품 Summary'][row][col]=value
    with pytest.raises(ValueError):si.parse(data,'2026-05')


@pytest.fixture
def source(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path);store.init()
    monkeypatch.setattr(imports,'tables',lambda path:umicore())
    path=tmp_path/'renamed.csv';path.write_text('source',encoding='utf-8')
    return imports.register(path)['id']


def test_simple_register_comparison_no_duplicate_receipts_and_delete(source):
    sid=source
    p=si.preview(sid,'2026-05')
    assert not p['comparison']['erp_available']
    si.apply(sid,{'period':'2026-05','fingerprint':p['fingerprint']})
    p=si.preview(sid,'2026-05')
    assert si.apply(sid,{'period':'2026-05','fingerprint':p['fingerprint']})['duplicate']
    with store.db() as c:assert c.execute('SELECT COUNT(*) FROM records').fetchone()[0]==0
    assert si.preview(sid,'2026-06')['errors']
    imports.commit_rows([{'kind':'receipt','part':'28991-4C520','customer':'현대 전주','date':'2026-05-31','quantity':'12'}],None,'erp-test','append')
    p=si.preview(sid,'2026-05')
    assert p['comparison']['differences'][0]['difference']=='2'
    with pytest.raises(ValueError,match='마감자료'):imports.mapped_rows(sid,{})
    impact=source_lifecycle.impact(sid)
    source_lifecycle.change(sid,{'fingerprint':impact['fingerprint'],'reason':'test','confirm':True})
    with store.db() as c:assert si.registered(c)==[]
    with pytest.raises(ValueError):si.preview(sid,'2026-05')


def test_replacement_and_stale_preview(source):
    p=si.preview(source,'2026-05')
    with store.db() as c:store.audit(c,'test',{})
    with pytest.raises(ValueError,match='변경'):si.apply(source,{'period':'2026-05','fingerprint':p['fingerprint']})
    p=si.preview(source,'2026-05');si.apply(source,{'period':'2026-05','fingerprint':p['fingerprint']})
    path=store.ROOT/'revision.csv';path.write_text('revision',encoding='utf-8')
    sid=imports.register(path)['id'];p=si.preview(sid,'2026-05')
    assert p['replaces'][0]['id']==source
    si.apply(sid,{'period':'2026-05','fingerprint':p['fingerprint']})
    with store.db() as c:assert [r['source_id'] for r in si.registered(c)]==[sid]
    assert not si.preview(source,'2026-05')['registered']


def test_existing_files_reclassified_and_api_preview(source):
    from fastapi.testclient import TestClient
    from catalyst.api import app
    with store.db() as c:
        meta=json.loads(c.execute('SELECT meta FROM sources WHERE id=?',(source,)).fetchone()[0]);meta['type']='주차별 발주납품'
        c.execute('UPDATE sources SET meta=? WHERE id=?',(store.encode(meta),source))
    client=TestClient(app)
    row=client.get('/api/sources').json()[0]
    assert row['meta']['type']==si.TYPES['umicore']
    assert 'umicore' in row['roles']
    assert client.post(f'/api/sources/{source}/supplier-preview',json={'period':'2026-05'}).json()['parts']==1


def test_legacy_mapped_ledger_is_blocked(source):
    imports.commit_rows([{'kind':'receipt','part':'28991-4C520','customer':'현대 전주','date':'2026-05-31','quantity':'10'}],source,'legacy','append')
    p=si.preview(source,'2026-05')
    assert p['errors']
    with pytest.raises(ValueError):si.apply(source,{'period':'2026-05','fingerprint':p['fingerprint']})


def test_real_may_and_august_sources_read_only():
    root=Path(__file__).resolve().parents[1]
    checked=0
    for base,period,expected in [(root/'5월','2026-05',{'umicore':'15131','heesung':'143489'}),(root,'2026-08',{'umicore':'11231','heesung':'97952'})]:
        for p in base.glob('*.xlsx'):
            if '유미코아' not in p.name and '출하실적' not in p.name:continue
            result=si.parse(imports.tables(p),period)
            assert result['totals']['delivery']==expected[result['supplier']]
            checked+=1
    if not checked:pytest.skip('Business workbooks not distributed with source')
