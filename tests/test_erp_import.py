import copy
import json
from pathlib import Path
import pytest
from catalyst import erp_import,imports,store,source_roles


def table():
    return {'ERP':[
        ['기간별구매거래처입고현황'],
        ['품목자산분류','품명','품번','규격','단위','화폐','합계','현대모비스(주)','현대자동차(주)전주'],
        ['품목자산분류','품명','품번','규격','단위','화폐','수량계','수량','수량'],
        ['TOTAL','','','','','',8,5,3],
        ['4.촉매,컨버터','CATALYST-FR','R60028991-4C520','','EA','KRW',5,2,3],
        ['4.촉매,컨버터','CONVERTER','R600289E0-4A120','','EA','KRW',3,3,0],
    ]}


def test_crosstab_totals_date_and_exclusion():
    r=erp_import.parse(table(),'2026-05',{'source_id':1})
    assert r['date']=='2026-05-31' and r['count']==2
    assert r['total']=='8' and r['excluded_total']=='3' and r['receipt_total']=='5'
    assert r['rows'][1]['customer']=='현대 전주'
    assert r['rows'][1]['part']=='28991-4C520'
    assert r['rows'][1]['provenance']['column']==9
    assert 'price' not in r['rows'][1]


@pytest.mark.parametrize('row,col,value',[(4,6,99),(3,6,99),(3,7,99),(1,7,'미등록 거래처'),(4,5,'USD'),(4,1,'OTHER')])
def test_bad_totals_or_schema_rejected(row,col,value):
    data=table();data['ERP'][row][col]=value
    with pytest.raises(ValueError):erp_import.parse(data,'2026-05',{})


def test_period_required_and_legacy_metadata_recognition():
    with pytest.raises(ValueError):erp_import.parse(table(),'20260921',{})
    meta={'sheets':[{'headers':[{'row':i+1,'cells':r} for i,r in enumerate(table()['ERP'][:3])]}]}
    assert erp_import.recognizes_meta(meta)
    assert not erp_import.recognizes_meta({'sheets':[{'headers':[]}]})
    assert 'receipt' in source_roles.describe({'type':erp_import.TYPE},[])['roles']


@pytest.fixture
def source(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path);store.init()
    path=tmp_path/'renamed.csv';path.write_text('placeholder',encoding='utf-8')
    monkeypatch.setattr(imports,'tables',lambda path:table())
    sid=imports.register(path)['id']
    return sid


def test_apply_duplicates_and_safe_replacement(source):
    sid=source
    r=erp_import.preview(sid,'2026-05')
    with pytest.raises(ValueError):erp_import.apply(sid,{'period':'2026-05','fingerprint':r['fingerprint']})
    erp_import.apply(sid,{'period':'2026-05','fingerprint':r['fingerprint'],'confirm_period':True})
    assert erp_import.preview(sid,'2026-05')['errors']
    assert erp_import.preview(sid,'2026-06')['errors']
    with pytest.raises(ValueError):imports.mapped_rows(sid,{'sheet':'ERP','header_row':3})
    path=store.ROOT/'changed.csv';path.write_text('changed',encoding='utf-8')
    new=imports.register(path)['id']
    r=erp_import.preview(new,'2026-05');assert r['replace_count']==2
    erp_import.apply(new,{'period':'2026-05','fingerprint':r['fingerprint'],'confirm_period':True})
    with store.db() as c:
        assert c.execute('SELECT COUNT(*) FROM records r JOIN batches b ON b.id=r.batch_id WHERE b.active=1').fetchone()[0]==2


def test_other_month_preserved_and_manual_conflict(source):
    imports.commit_rows([{'kind':'receipt','part':'P','customer':'C','date':'2026-04-30','quantity':1}],None,'manual','append')
    r=erp_import.preview(source,'2026-05');assert not r['errors']
    imports.commit_rows([{'kind':'receipt','part':'P','customer':'C','date':'2026-05-31','quantity':1}],None,'manual2','append')
    with pytest.raises(ValueError):erp_import.apply(source,{'period':'2026-05','fingerprint':r['fingerprint'],'confirm_period':True})
    assert erp_import.preview(source,'2026-05')['errors']


def test_stale_preview_rejected(source):
    r=erp_import.preview(source,'2026-05')
    with store.db() as c:store.audit(c,'intervening',{})
    with pytest.raises(ValueError,match='다시 미리보기'):
        erp_import.apply(source,{'period':'2026-05','fingerprint':r['fingerprint'],'confirm_period':True})

def test_existing_pending_source_reclassified_and_preview_api(source):
    from catalyst.api import sources,erp_preview
    with store.db() as c:
        meta=json.loads(c.execute('SELECT meta FROM sources WHERE id=?',(source,)).fetchone()[0])
        meta['type']='열 연결 필요'
        c.execute('UPDATE sources SET meta=? WHERE id=?',(store.encode(meta),source))
    row=sources()[0]
    assert row['meta']['type']==erp_import.TYPE and row['status']=='pending'
    assert row['roles']==['receipt']
    result=erp_preview(source,{'period':'2026-05'})
    assert result['receipt_total']=='5' and result['count']==2
