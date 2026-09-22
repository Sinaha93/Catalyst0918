import json
import shutil
from pathlib import Path
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

def remove(sid):
    return lifecycle.change(sid,{'fingerprint':lifecycle.impact(sid)['fingerprint'],'reason':'시험','confirm':True})

def test_delete_registration_preserves_all_files(db):
    sid,path=source(db)
    uploaded=db/'input'/'upload.csv';shutil.copy2(path,uploaded)
    assert lifecycle.impact(sid)['delete_files']==[]
    result=remove(sid)
    assert result['deleted_files']==0 and result['warnings']==[]
    assert path.exists() and uploaded.exists()
    assert uploaded.read_bytes()==path.read_bytes()
    assert len(list((db/'archive').iterdir()))==1
    assert imports.register(path)['status']=='deleted'
    with pytest.raises(ValueError,match='이미 삭제'):remove(sid)
    with pytest.raises(ValueError):imports.commit_rows([{'kind':'part','part':'X','date':'2026-08-01'}],sid,'new','append')
    with store.db() as c:assert c.execute('SELECT SUM(active) FROM batches').fetchone()[0]==0

def test_frozen_evidence_preserved(db):
    sid,path=source(db)
    with store.db() as c:
        c.execute('INSERT INTO runs(period,version,snapshot,created) VALUES(?,?,?,?)',('2026-08',1,json.dumps({'source_ids':[sid],'value':123}),store.stamp()))
    view=lifecycle.impact(sid)
    assert len(view['retained_files'])==1 and not view['delete_files']
    remove(sid)
    assert len(list((db/'archive').iterdir()))==1
    with store.db() as c:assert json.loads(c.execute('SELECT snapshot FROM runs').fetchone()[0])['value']==123

def test_old_superseded_batch_does_not_delete_current(db):
    old,_=source(db)
    current,_=source(db,'b',quantity=2)
    assert lifecycle.impact(old)['count']==0
    remove(old)
    with store.db() as c:assert c.execute('SELECT source_id FROM batches WHERE active=1').fetchone()[0]==current

def test_stale_preview_reason_and_confirmation(db):
    sid,_=source(db);fingerprint=lifecycle.impact(sid)['fingerprint']
    with pytest.raises(ValueError):lifecycle.change(sid,{'fingerprint':fingerprint})
    with pytest.raises(ValueError):lifecycle.change(sid,{'fingerprint':fingerprint,'reason':'시험'})
    with store.db() as c:store.audit(c,'intervening',{})
    with pytest.raises(ValueError,match='다시 확인'):lifecycle.change(sid,{'fingerprint':fingerprint,'reason':'시험','confirm':True})

def test_linked_sources_and_manual_derivatives(db):
    first,_=source(db,'a','paired')
    path=db/'b.csv';path.write_text('x,y',encoding='utf-8')
    second=imports.register(path)['id']
    imports.commit_rows([{'kind':'part','part':'P','date':'2026-08-01'}],second,'paired','append')
    imports.commit_rows([{'kind':'part','part':'Q','date':'2026-08-01','provenance':{'source_id':first}}],None,'manual-derived','append')
    view=lifecycle.impact(first)
    assert len(view['sources'])==2 and view['count']==3
    remove(first)
    with store.db() as c:
        assert c.execute('SELECT SUM(active) FROM batches').fetchone()[0]==0
        assert c.execute('SELECT status FROM sources WHERE id=?',(second,)).fetchone()[0]=='deleted'

def test_locked_file_does_not_prevent_registration_removal(db,monkeypatch):
    sid,path=source(db);uploaded=db/'input'/'uploaded.csv';shutil.copy2(path,uploaded)
    original=Path.rename
    def rename(self,target):
        if self==uploaded:raise PermissionError('locked')
        return original(self,target)
    monkeypatch.setattr(Path,'rename',rename)
    remove(sid)
    assert uploaded.exists() and len(list((db/'archive').iterdir()))==1
    assert not any(p.name.startswith('.deleting-') for p in (db/'archive').iterdir())
    with store.db() as c:assert c.execute('SELECT active FROM batches').fetchone()[0]==0

def test_explicit_reregistration_allowed_but_watch_cannot_restore(db):
    sid,path=source(db)
    remove(sid)
    assert imports.register(path)['status']=='deleted'
    assert imports.register(path,allow_deleted=True)['duplicate'] is False
    row={'kind':'receipt','part':'P','customer':'C','date':'2026-08-01','quantity':1}
    imports.commit_rows([row],sid,'receipts','replace')
    with pytest.raises(ValueError):imports.commit_rows([row],sid,'receipts','append')
    with store.db() as c:assert c.execute('SELECT COUNT(*) FROM batches WHERE active=1').fetchone()[0]==1


def test_reset_all_registrations_keeps_files_manual_and_frozen(db):
    first,path=source(db)
    imports.commit_rows([{'kind':'price','part':'MANUAL','date':'2026-08-01','price':'2'}],None,'manual-price','append')
    imports.commit_rows([{'kind':'receipt','part':'DERIVED','customer':'C','date':'2026-08-01','quantity':'3','provenance':{'source_id':first}},
                         {'kind':'receipt','part':'KEEP','customer':'C','date':'2026-08-01','quantity':'4'}],None,'mixed','append')
    output=db/'outputs'/'report.xlsx';output.write_bytes(b'keep')
    with store.db() as c:
        c.execute('INSERT INTO runs(period,version,snapshot,created) VALUES(?,?,?,?)',('2026-08',1,json.dumps({'source_ids':[first]}),store.stamp()))
    p=lifecycle.reset_impact()
    assert p['count']==2 and p['manual_count']==2 and p['runs']==1
    result=lifecycle.reset_registrations({'fingerprint':p['fingerprint'],'confirm_text':'초기화'})
    assert result['deleted_files']==0 and (db/'backups'/result['backup']).exists()
    assert path.exists() and output.exists() and len(list((db/'archive').iterdir()))==1
    assert imports.register(path)['status']=='deleted'
    with store.db() as c:
        assert {r[0] for r in c.execute('SELECT part FROM records r JOIN batches b ON b.id=r.batch_id WHERE b.active=1')}=={'MANUAL','KEEP'}
        assert c.execute('SELECT count(*) FROM runs').fetchone()[0]==1
    assert imports.register(path,allow_deleted=True)['duplicate'] is False


def test_reset_requires_confirmation_fresh_preview_and_idle_jobs(db):
    source(db);p=lifecycle.reset_impact()
    with pytest.raises(ValueError,match='확인란'):lifecycle.reset_registrations({'fingerprint':p['fingerprint']})
    with store.db() as c:store.audit(c,'change',{})
    with pytest.raises(ValueError,match='변경'):lifecycle.reset_registrations({'fingerprint':p['fingerprint'],'confirm_text':'초기화'})
    with store.db() as c:c.execute('INSERT INTO jobs VALUES(?,?,?,?,?)',('job','running','',None,store.stamp()))
    with pytest.raises(ValueError,match='작업'):lifecycle.reset_impact()
