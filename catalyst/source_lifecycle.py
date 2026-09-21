"""Recoverable registration cancellation; originals and frozen closes never change."""
import hashlib
import json
from . import store


def impact(sid):
    with store.db() as c:
        source=c.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
        if not source: raise ValueError('등록 자료를 찾을 수 없습니다')
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
        result['frozen_runs']=[{'period':r['period'],'version':r['version']} for r in c.execute('SELECT * FROM runs') if ids.intersection(json.loads(r['snapshot']).get('source_ids',[]))]
        # Any intervening write requires the user to preview again.
        revision=c.execute('SELECT COALESCE(MAX(id),0) FROM audit').fetchone()[0]
        result['fingerprint']=hashlib.sha256((store.encode(result)+str(revision)).encode()).hexdigest()
        return result


def change(sid,payload):
    reason=str(payload.get('reason','')).strip()
    if not reason: raise ValueError('삭제·복원 사유를 입력해주세요')
    current=impact(sid)
    if payload.get('fingerprint')!=current['fingerprint']:
        raise ValueError('자료가 변경되었습니다. 영향 범위를 다시 확인해주세요')
    backup=store.backup()
    with store.db() as c:
        if current['cancelled']:
            for b in current['batches']:
                if c.execute('SELECT 1 FROM batches WHERE active=1 AND scope=?',(b['scope'],)).fetchone():
                    raise ValueError('동일 자료 묶음의 새 자료가 반영되어 복원할 수 없습니다. 새 자료를 먼저 취소해주세요.')
                for row in c.execute("SELECT * FROM records WHERE batch_id=? AND kind='price'",(b['id'],)):
                    matches=c.execute("SELECT r.id,r.price FROM records r JOIN batches b ON b.id=r.batch_id WHERE b.active=1 AND r.kind='price' AND r.part=? AND r.customer=? AND r.date=?",(row['part'],row['customer'],row['date'])).fetchall()
                    from decimal import Decimal
                    if any(Decimal(r['price'])!=Decimal(row['price']) and r['id'] not in current.get('existing_price_ids',[]) for r in matches):
                        raise ValueError('복원 단가가 현재 단가와 충돌합니다')
            for b in current['batches']: c.execute('UPDATE batches SET active=1 WHERE id=?',(b['id'],))
            for s in current['sources']: c.execute('UPDATE sources SET status=? WHERE id=?',(s['status'],s['id']))
            c.execute('UPDATE source_cancellations SET restored=1 WHERE id=?',(current['cancel_id'],))
            action='restore_source'
        else:
            for b in current['batches']: c.execute('UPDATE batches SET active=0 WHERE id=?',(b['id'],))
            for s in current['sources']: c.execute("UPDATE sources SET status='cancelled' WHERE id=?",(s['id'],))
            c.execute('INSERT INTO source_cancellations(source_ids,snapshot,created) VALUES(?,?,?)',(store.encode([s['id'] for s in current['sources']]),store.encode(current),store.stamp()))
            action='cancel_source'
        store.audit(c,action,{'source_id':sid,'reason':reason,'backup':backup,'impact':current})
    return {'backup':backup,'count':current['count']}
