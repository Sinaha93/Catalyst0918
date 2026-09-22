import json
import pytest
from catalyst import store, imports, supplier_import as si, supplier_allocation as sa, closing


@pytest.fixture
def source(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path);store.init()
    data={'5월 마감':[[None,2,10,5,4,9,12,3],['품번','적송(이월)','출하','아산','모비스','계','적송+출하','차이'],['28957-03CR0',2,10,5,4,9,12,3]]}
    monkeypatch.setattr(imports,'tables',lambda path:data)
    path=tmp_path/'supplier.csv';path.write_text('evidence',encoding='utf-8')
    sid=imports.register(path)['id'];p=si.preview(sid,'2026-05')
    si.apply(sid,{'period':'2026-05','fingerprint':p['fingerprint']})
    return sid,data


def test_exact_supplier_settlement_and_ambiguous_opening(source):
    sid,_=source
    p=closing.preview('2026-05')
    auto=[r for r in p['input_snapshot'] if r['scope']=='supplier-derived:2026-05']
    assert {(r['customer'],r['quantity']) for r in auto if r['kind']=='settlement'}=={('현대 아산','5'),('현대 모비스','4')}
    assert not any(r['kind']=='receipt' for r in auto)
    assert p['supplier_allocation']['pending'][0]['total']=='2'
    assert not p['ready']
    with store.db() as c:assert c.execute('SELECT count(*) FROM records').fetchone()[0]==0
    assert closing.preview('2026-06')['supplier_allocation']['source_ids']==[]


def test_manual_split_sum_staleness_and_reuse(source):
    sid,_=source;p=closing.preview('2026-05')
    payload={'source_id':sid,'period':'2026-05','part':'28957-03CR0','kind':'opening','fingerprint':p['fingerprint'],'reason':'전월 확인','values':{'현대 아산':'1','현대 모비스':'1'}}
    with pytest.raises(ValueError,match='합계'):sa.save({**payload,'values':{'현대 아산':'5'}})
    with pytest.raises(ValueError,match='사유'):sa.save({**payload,'reason':''})
    with pytest.raises(ValueError):sa.save({**payload,'values':{'unknown':'2'}})
    sa.save(payload)
    p2=closing.preview('2026-05')
    assert p2['supplier_allocation']['pending']==[]
    assert sum(int(r['quantity']) for r in p2['input_snapshot'] if r['kind']=='opening')==2
    assert p2['fingerprint']!=p['fingerprint']
    assert closing.preview('2026-05')['fingerprint']==p2['fingerprint']
    with pytest.raises(ValueError,match='변경'):sa.save(payload)


def test_prior_preserves_amount_and_conflicts_block(source):
    sid,_=source
    prior={'details':[{'part':'28957-03CR0','customer':'현대 아산','closing':'2','closing_amount':'987'}]}
    with store.db() as c:c.execute('INSERT INTO runs(period,version,snapshot,created) VALUES(?,?,?,?)',('2026-04',1,store.encode(prior),store.stamp()))
    p=closing.preview('2026-05')
    assert not any(r['kind']=='opening' for r in p['input_snapshot'])
    assert next(r for r in p['details'] if r['customer']=='현대 아산')['opening_amount']=='987'
    imports.commit_rows([{'kind':'settlement','part':'28957-03CR0','customer':'현대 아산','quantity':'9','date':'2026-05-31'}],None,'manual','append')
    p=closing.preview('2026-05')
    assert any(r['kind']=='settlement' and not r['editable'] for r in p['supplier_allocation']['pending'])
    assert len([r for r in p['input_snapshot'] if r['kind']=='settlement'])==1


def test_source_deletion_removes_derived_records_and_uncovered_erp_blocks(source):
    sid,_=source
    imports.commit_rows([{'kind':'receipt','part':'OTHER-00000','customer':'현대 아산','quantity':'1','date':'2026-05-31'}],None,'erp','append')
    p=closing.preview('2026-05');assert any(r['code']=='supplier_coverage' for r in p['issues'])
    with store.db() as c:c.execute("UPDATE sources SET status='deleted' WHERE id=?",(sid,))
    p=closing.preview('2026-05');assert not p['supplier_allocation']['source_ids']
    assert not any(r.get('scope')=='supplier-derived:2026-05' for r in p['input_snapshot'])


def test_zero_residue_exact_opening_allocation(source):
    _,data=source
    # Opening 2 + receipts 10 = settlement 12; no remainder.
    data['5월 마감'][0]=[None,2,10,7,5,12,12,0]
    data['5월 마감'][2]=['28957-03CR0',2,10,7,5,12,12,0]
    imports.commit_rows([{'kind':'receipt','part':'28957-03CR0','customer':c,'quantity':q,'date':'2026-05-31'} for c,q in [('현대 아산','6'),('현대 모비스','4')]],None,'erp','append')
    p=closing.preview('2026-05')
    assert not p['supplier_allocation']['pending']
    assert {(r['customer'],r['quantity']) for r in p['input_snapshot'] if r['kind']=='opening'}=={('현대 아산','1'),('현대 모비스','1')}


def test_zero_delivery_needs_full_month_erp(source):
    _,data=source
    data['5월 마감'][0]=[None,2,0,0,2,2,2,0]
    data['5월 마감'][2]=['28957-03CR0',2,0,0,2,2,2,0]
    assert closing.preview('2026-05')['supplier_allocation']['pending']
    imports.commit_rows([{'kind':'receipt','part':'OTHER-00000','customer':'현대 아산','quantity':'1','date':'2026-05-31'}],None,'erp-monthly-receipt:2026-05','append')
    p=closing.preview('2026-05')
    assert not p['supplier_allocation']['pending']
    assert [(r['customer'],r['quantity']) for r in p['input_snapshot'] if r['kind']=='opening']==[('현대 모비스','2')]


def test_current_bom_removes_old_membership_preserves_new_manual():
    records=[{'kind':'part','part':'P','customer':'현대 전주','date':'2026-05-01','imported_at':'2026-09-21','provenance':json.dumps({'link':{'factory':'전주'}})}]
    links=[{'part':'P','customer':'현대 글로비스','updated':'2026-09-18'}]
    assert sa.effective_candidates('P',records,links)=={'현대 전주'}
    links[0]['updated']='2026-09-22'
    assert sa.effective_candidates('P',records,links)=={'현대 전주','현대 글로비스'}


def test_advanced_rule_month_scope_and_allocation_reedit(source):
    from catalyst import advanced
    sid,_=source
    rule={'period':'2026-05','part':'28957-03CR0','customer':'현대 모비스','reason':'직사급 확인','enabled':True,'before':None}
    advanced.save_rule(rule)
    p=closing.preview('2026-05')
    assert not p['supplier_allocation']['pending']
    assert {r['customer'] for r in p['input_snapshot']}=={'현대 모비스'}
    payload={'source_id':sid,'period':'2026-05','part':'28957-03CR0','kind':'settlement','fingerprint':p['fingerprint'],'reason':'분할 정정','values':{'현대 아산':'5','현대 모비스':'4'}}
    sa.save(payload)
    p=closing.preview('2026-05')
    sa.save({**payload,'fingerprint':p['fingerprint'],'values':{'현대 아산':'6','현대 모비스':'3'}})
    entry=next(r for r in closing.preview('2026-05')['supplier_allocation']['entries'] if r['kind']=='settlement')
    assert entry['values']=={'현대 아산':'6','현대 모비스':'3'}
    assert not closing.preview('2026-06')['supplier_allocation']['source_ids']
    history=advanced.history()['items']
    assert history[0]['detail']['before']=={'현대 아산':'5','현대 모비스':'4'}
    with pytest.raises(ValueError,match='변경'):advanced.save_rule(rule)
    before=advanced.rules()[0]
    advanced.save_rule({**rule,'before':before,'enabled':False})
    assert closing.preview('2026-05')['supplier_allocation']['pending'][0]['kind']=='opening'


def test_umicore_remarks_only_allocate_settlement_when_erp_matches(source):
    _,data=source
    data.clear()
    data['납품 Summary']=[['품번','전월적송재고','Total 납품','당월마감수량','','당월적송수량','비고'],
        [None,None,None,'1차','Total'],['28957-03CR0',9,400,None,400,9,'50개 글로비스+350개 전주'],
        [None,9,400,None,400,9]]
    data['납품 Summary']=[['Total' if i==3 else None]+row for i,row in enumerate(data['납품 Summary'])]
    imports.commit_rows([{'kind':'receipt','part':'28957-03CR0','customer':c,'quantity':q,'date':'2026-05-31'} for c,q in [('현대 글로비스','50'),('현대 전주','350')]],None,'erp-monthly-receipt:2026-05','append')
    p=closing.preview('2026-05')
    assert [r['kind'] for r in p['supplier_allocation']['pending']]==['opening']
    assert {(r['customer'],r['quantity']) for r in p['input_snapshot'] if r['kind']=='settlement'}=={('현대 글로비스','50'),('현대 전주','350')}
    data['납품 Summary'][2][7]='51개 글로비스+349개 전주'
    assert {r['kind'] for r in closing.preview('2026-05')['supplier_allocation']['pending']}=={'opening','settlement'}
