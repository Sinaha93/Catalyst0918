import json
import pytest
from catalyst import store, imports, source_lifecycle as lifecycle


@pytest.fixture
def db(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path)
    store.init()
    return tmp_path


def source(db,name='a',scope='receipts',quantity=1):
    path=db/(name+'.csv');path.write_text('part,quantity\nP,'+str(quantity),encoding='utf-8')
    sid=imports.register(path)['id']
    imports.commit_rows([{'kind':'receipt','part':'P','customer':'C','date':'2026-08-01','quantity':quantity}],sid,scope,'replace')
    return sid,path


def toggle(sid):
    return lifecycle.change(sid,{'fingerprint':lifecycle.impact(sid)['fingerprint'],'reason':'시험'})


def test_cancel_restore_duplicates_and_snapshot(db):
    sid,path=source(db)
    with store.db() as c:
        c.execute('INSERT INTO runs(period,version,snapshot,created) VALUES(?,?,?,?)',('2026-08',1,json.dumps({'source_ids':[sid],'value':123}),store.stamp()))
    assert lifecycle.impact(sid)['count']==1
    toggle(sid)
    assert imports.register(path)['status']=='cancelled'
    with pytest.raises(ValueError):imports.commit_rows([{'kind':'part','part':'X','date':'2026-08-01'}],sid,'new','append')
    with store.db() as c:
        assert c.execute('SELECT SUM(active) FROM batches').fetchone()[0]==0
        assert json.loads(c.execute('SELECT snapshot FROM runs').fetchone()[0])['value']==123
    assert path.exists()
    toggle(sid)
    with store.db() as c:assert c.execute('SELECT SUM(active) FROM batches').fetchone()[0]==1


def test_old_superseded_batches_never_restore(db):
    old,_=source(db)
    current,_=source(db,'b',quantity=2)
    assert lifecycle.impact(old)['count']==0
    toggle(old);toggle(old)
    with store.db() as c:
        assert c.execute('SELECT source_id FROM batches WHERE active=1').fetchone()[0]==current


def test_new_replacement_blocks_restore(db):
    sid,_=source(db);toggle(sid)
    source(db,'b',quantity=2)
    with pytest.raises(ValueError,match='새 자료'):toggle(sid)


def test_stale_preview_and_reason(db):
    sid,_=source(db);fingerprint=lifecycle.impact(sid)['fingerprint']
    with pytest.raises(ValueError):lifecycle.change(sid,{'fingerprint':fingerprint})
    with store.db() as c:store.audit(c,'intervening',{})
    with pytest.raises(ValueError,match='다시 확인'):lifecycle.change(sid,{'fingerprint':fingerprint,'reason':'시험'})


def test_linked_sources_and_manual_derivatives(db):
    first,_=source(db,'a','paired')
    second_path=db/'b.csv';second_path.write_text('x,y',encoding='utf-8')
    second=imports.register(second_path)['id']
    imports.commit_rows([{'kind':'part','part':'P','date':'2026-08-01'}],second,'paired','append')
    imports.commit_rows([{'kind':'part','part':'Q','date':'2026-08-01','provenance':{'source_id':first}}],None,'manual-derived','append')
    view=lifecycle.impact(first)
    assert len(view['sources'])==2 and view['count']==3
    toggle(first)
    assert lifecycle.impact(second)['cancelled']
    toggle(second)
    with store.db() as c:assert c.execute('SELECT SUM(active) FROM batches').fetchone()[0]==3
