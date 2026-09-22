"""Remove registrations from active calculations without deleting any files."""
import hashlib
import json
from pathlib import Path
from . import store


def reset_impact():
    with store.db() as c:
        if c.execute("SELECT 1 FROM jobs WHERE state='running'").fetchone():
            raise ValueError('자료 처리 작업이 끝난 후 초기화해주세요.')
        sources=[dict(r) for r in c.execute("SELECT id,name,status,meta FROM sources WHERE status!='deleted' ORDER BY id")]
        ids={s['id'] for s in sources}
        records=[dict(r) for r in c.execute('SELECT r.*,b.source_id FROM records r JOIN batches b ON b.id=r.batch_id WHERE b.active=1 ORDER BY r.id')]
        selected=[r for r in records if r['source_id'] in ids or json.loads(r['provenance']).get('source_id') in ids]
        periods={r['date'][:7] for r in selected}
        for s in sources:
            info=json.loads(s.pop('meta')).get('supplier_registration',{})
            if info.get('active'):periods.add(info['period'])
        result={'sources':sources,'record_ids':[r['id'] for r in selected],'count':len(selected),
                'periods':sorted(periods),'manual_count':len(records)-len(selected),
                'runs':c.execute('SELECT count(*) FROM runs').fetchone()[0]}
        revision=c.execute('SELECT COALESCE(MAX(id),0) FROM audit').fetchone()[0]
        result['fingerprint']=hashlib.sha256((store.encode(result)+str(revision)).encode()).hexdigest()
        return result


def reset_registrations(payload):
    current=reset_impact()
    if payload.get('confirm_text')!='초기화':raise ValueError('확인란에 초기화를 입력해주세요.')
    if payload.get('fingerprint')!=current['fingerprint']:raise ValueError('자료가 변경되었습니다. 초기화 범위를 다시 확인해주세요.')
    if not current['sources']:raise ValueError('초기화할 등록 자료가 없습니다.')
    backup=store.backup()
    selected=set(current['record_ids']);source_ids={s['id'] for s in current['sources']}
    with store.db() as c:
        for batch in c.execute('SELECT * FROM batches WHERE active=1').fetchall():
            rows=c.execute('SELECT * FROM records WHERE batch_id=?',(batch['id'],)).fetchall()
            if batch['source_id'] not in source_ids and not any(r['id'] in selected for r in rows):continue
            c.execute('UPDATE batches SET active=0 WHERE id=?',(batch['id'],))
            kept=[r for r in rows if r['id'] not in selected]
            if kept:
                bid=c.execute('INSERT INTO batches(source_id,scope,mode,created) VALUES(NULL,?,?,?)',(batch['scope'],'append',store.stamp())).lastrowid
                for r in kept:
                    keys=('kind','part','customer','date','quantity','price','amount','note','provenance')
                    c.execute('INSERT INTO records(batch_id,kind,part,customer,date,quantity,price,amount,note,provenance) VALUES(?,?,?,?,?,?,?,?,?,?)',(bid,*(r[k] for k in keys)))
        for sid in source_ids:
            c.execute("UPDATE sources SET status='deleted' WHERE id=?",(sid,))
            c.execute('UPDATE issues SET resolved=1 WHERE source_id=?',(sid,))
        store.audit(c,'reset_registrations',{'impact':current,'backup':backup})
    return {'sources':len(source_ids),'count':len(selected),'backup':backup,'deleted_files':0}


def impact(sid):
    with store.db() as c:
        source=c.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
        if not source: raise ValueError('등록 자료를 찾을 수 없습니다')
        if source['status']=='deleted': raise ValueError('이미 삭제한 자료입니다')
        if source['status']=='cancelled':
            for event in c.execute('SELECT * FROM source_cancellations WHERE restored=0 ORDER BY id DESC'):
                if sid in json.loads(event['source_ids']):
                    snapshot=json.loads(event['snapshot'])
                    result={**snapshot,'cancel_id':event['id'],'cancelled':True}
                    break
            else: raise ValueError('취소 이력을 찾을 수 없습니다')
        else:
            batches=[dict(r) for r in c.execute('SELECT * FROM batches WHERE active=1')]
            all_records=[dict(r) for r in c.execute('SELECT * FROM records')]
            ids={sid}
            # Bootstrap and paired master imports are indivisible dependency groups.
            while True:
                derived={r['batch_id'] for r in all_records if json.loads(r['provenance']).get('source_id') in ids}
                scopes={b['scope'] for b in batches if b['source_id'] in ids or b['id'] in derived}
                linked={b['source_id'] for b in batches if b['scope'] in scopes and b['source_id']}
                expanded=ids|linked
                if expanded==ids: break
                ids=expanded
            selected=[b for b in batches if b['source_id'] in ids or (b['source_id'] is None and b['id'] in derived)]
            bid={b['id'] for b in selected}
            records=[r for r in all_records if r['batch_id'] in bid]
            sources=[dict(r) for r in c.execute('SELECT id,name,status FROM sources') if r['id'] in ids]
            result={'sources':sources,'batches':selected,'count':len(records),
                    'periods':sorted({r['date'][:7] for r in records}),
                    'master':any(r['kind'] in ('part','price') for r in records),
                    'existing_price_ids':[r['id'] for r in all_records if r['kind']=='price' and r['batch_id'] not in bid and any(b['id']==r['batch_id'] for b in batches)],
                    'cancelled':False}
        ids={s['id'] for s in result['sources']}
        comparisons=[]
        for s in c.execute('SELECT id,meta FROM sources'):
            info=json.loads(s['meta']).get('supplier_registration')
            if s['id'] in ids and info and info.get('active'):
                comparisons.append({'source_id':s['id'],'period':info['period'],'parts':info['parts']})
        result['supplier_comparisons']=comparisons
        result['periods']=sorted(set(result['periods'])|{r['period'] for r in comparisons})
        result['frozen_runs']=[{'period':r['period'],'version':r['version']} for r in c.execute('SELECT * FROM runs') if ids.intersection(json.loads(r['snapshot']).get('source_ids',[]))]
        result['delete_files']=[]
        result['retained_files']=[]
        for s in c.execute('SELECT * FROM sources'):
            if s['id'] not in ids:continue
            digest=s['hash']; suffix=Path(s['path']).suffix.lower()
            path=store.ROOT/'archive'/(digest+suffix)
            if path.exists():result['retained_files'].append(str(path))
        result['deletion_mode']='registration_only'
        # Any intervening write requires the user to preview again.
        revision=c.execute('SELECT COALESCE(MAX(id),0) FROM audit').fetchone()[0]
        result['fingerprint']=hashlib.sha256((store.encode(result)+str(revision)).encode()).hexdigest()
        return result


def change(sid,payload):
    reason=str(payload.get('reason','')).strip()
    if not reason: raise ValueError('삭제 사유를 입력해주세요')
    current=impact(sid)
    if payload.get('fingerprint')!=current['fingerprint']:
        raise ValueError('자료가 변경되었습니다. 영향 범위를 다시 확인해주세요')
    if payload.get('confirm') is not True:raise ValueError('프로그램 등록 삭제를 확인해주세요')
    with store.db() as c:
        for b in current['batches']: c.execute('UPDATE batches SET active=0 WHERE id=?',(b['id'],))
        for s in current['sources']: c.execute("UPDATE sources SET status='deleted' WHERE id=?",(s['id'],))
        store.audit(c,'delete_source',{'source_id':sid,'reason':reason,'impact':current,'mode':'registration_only'})
    return {'count':current['count'],'deleted_files':0,'retained_files':len(current['retained_files']),'warnings':[]}
