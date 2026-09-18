import asyncio
import json
import sys
import threading
import uuid
import shutil
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, UploadFile, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from . import store, imports, closing, estimates

LOCK=threading.RLock()

def job(fn):
    jid=uuid.uuid4().hex
    with store.db() as c:
        c.execute('INSERT INTO jobs VALUES(?,?,?,?,?)',(jid,'running','처리 중',None,store.stamp()))
    def run():
        try:
            with LOCK:
                result=fn()
            state,message='done','완료'
        except Exception as e:
            result,state,message=None,'failed',str(e)
        with store.db() as c:
            c.execute('UPDATE jobs SET state=?,message=?,result=? WHERE id=?',(state,message,store.encode(result),jid))
    threading.Thread(target=run,daemon=True).start()
    return {'job_id':jid}

async def watch():
    observed={}
    processed={}
    while True:
        await asyncio.sleep(5)
        for path in (store.ROOT/'input').glob('*'):
            if path.suffix.lower() not in ('.xlsx','.csv','.pptx') or path.name.startswith('~$'):
                continue
            try:
                stat=path.stat()
                value=(stat.st_size,stat.st_mtime_ns)
                if observed.get(path)==value and processed.get(path)!=value:
                    await asyncio.to_thread(locked_register,path)
                    processed[path]=value
                observed[path]=value
            except (OSError,ValueError):
                continue

def locked_register(path):
    with LOCK:
        return imports.register(path)

@asynccontextmanager
async def lifespan(app):
    store.init()
    with store.db() as c:
        c.execute("UPDATE jobs SET state='failed',message='프로그램 종료로 중단되었습니다. 다시 실행해주세요.' WHERE state='running'")
    store.backup()
    task=asyncio.create_task(watch())
    yield
    task.cancel()

app=FastAPI(title='촉매 마감 관리',lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])

@app.middleware('http')
async def local_guard(request:Request,call_next):
    # Reject browser writes originating from unrelated sites.
    origin=request.headers.get('origin')
    if request.method not in ('GET','HEAD','OPTIONS') and origin and origin!=str(request.base_url).rstrip('/'):
        return JSONResponse({'detail':'다른 사이트에서 요청한 변경은 허용하지 않습니다'},status_code=403)
    return await call_next(request)

@app.exception_handler(ValueError)
async def bad_value(request,exc):
    return JSONResponse({'detail':str(exc)},status_code=422)

@app.get('/api/status')
def status():
    with store.db() as c:
        return {'app':'catalyst-closing','sources':c.execute('SELECT COUNT(*) FROM sources').fetchone()[0], 'records':c.execute('SELECT COUNT(*) FROM records r JOIN batches b ON b.id=r.batch_id WHERE b.active=1').fetchone()[0], 'pending':c.execute("SELECT COUNT(*) FROM sources WHERE status IN ('pending','error')").fetchone()[0], 'runs':c.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 'input_folder':str(store.ROOT/'input')}

@app.post('/api/shutdown')
def shutdown():
    with LOCK,store.db() as c:
        if c.execute("SELECT 1 FROM jobs WHERE state='running'").fetchone():raise ValueError('진행 중인 작업을 마친 후 종료해주세요')
    callback=getattr(app.state,'shutdown',None)
    if callback is None:raise ValueError('개발 서버는 실행 창에서 종료해주세요')
    store.backup()
    threading.Timer(.5,callback).start()
    return {'stopping':True}

@app.get('/api/sources')
def sources():
    with store.db() as c:
        return [{**dict(r),'meta':json.loads(r['meta'])} for r in c.execute('SELECT * FROM sources ORDER BY id DESC')]

@app.post('/api/scan')
def scan():
    def action():
        paths=[p for folder in (store.ROOT,store.ROOT/'input') for p in folder.glob('*') if p.suffix.lower() in ('.xlsx','.csv','.pptx') and not p.name.startswith('~$')]
        return [imports.register(p) for p in paths]
    return job(action)

@app.post('/api/upload')
async def upload(file:UploadFile):
    name=Path(file.filename or '').name
    if Path(name).suffix.lower() not in ('.xlsx','.csv','.pptx'):
        raise ValueError('xlsx, csv, pptx 파일을 선택해주세요')
    destination=store.ROOT/'input'/(uuid.uuid4().hex[:8]+'_'+name)
    content=await file.read(100*1024*1024+1)
    if len(content)>100*1024*1024:
        raise ValueError('파일은 100MB 이하여야 합니다')
    destination.write_bytes(content)
    return job(lambda:imports.register(destination))

@app.get('/api/sources/{sid}/download')
def original(sid:int):
    with store.db() as c:
        row=c.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
    if not row:
        raise HTTPException(404)
    return FileResponse(imports.source_path(row),filename=row['name'])

@app.post('/api/sources/{sid}/preview')
def map_preview(sid:int,config:dict):
    rows,sig=imports.mapped_rows(sid,config)
    errors=[]
    for i,r in enumerate(rows):
        try: imports.normalize(r)
        except Exception as e: errors.append({'row':r['provenance']['row'],'message':str(e)})
    return {'rows':rows[:30],'count':len(rows),'errors':errors[:50],'signature':sig}

@app.post('/api/sources/{sid}/apply')
def apply(sid:int,config:dict):
    return job(lambda:imports.apply(sid,config))

@app.get('/api/records')
def records():
    with store.db() as c:
        return [dict(r) for r in c.execute('SELECT r.*,b.scope,b.source_id FROM records r JOIN batches b ON b.id=r.batch_id WHERE b.active=1 ORDER BY r.id DESC LIMIT 1000')]

@app.get('/api/part-links')
def part_links():
    with store.db() as c:
        return [dict(r) for r in c.execute('SELECT * FROM part_links ORDER BY customer,part')]

@app.get('/api/price-estimates')
def price_estimates():
    with store.db() as c:
        return [dict(r) for r in c.execute('SELECT * FROM price_estimates ORDER BY period DESC,customer,part')]

@app.post('/api/price-estimates')
def save_price_estimate(payload:dict):
    with LOCK:
        return estimates.save(payload)

@app.post('/api/part-links')
def save_part_link(payload:dict):
    keys=('part','customer','factory','supplier','vehicle','price_type')
    row={k:str(payload.get(k,'')).strip() for k in keys}
    if not row['part'] or not row['customer']:raise ValueError('품번과 거래처가 필요합니다')
    if not str(payload.get('reason','')).strip():raise ValueError('변경 사유가 필요합니다')
    with LOCK,store.db() as c:
        old=c.execute('SELECT * FROM part_links WHERE part=? AND customer=?',(row['part'],row['customer'])).fetchone()
        c.execute('INSERT INTO part_links(part,customer,factory,supplier,vehicle,price_type,updated) VALUES(?,?,?,?,?,?,?) ON CONFLICT(part,customer) DO UPDATE SET factory=excluded.factory,supplier=excluded.supplier,vehicle=excluded.vehicle,price_type=excluded.price_type,updated=excluded.updated',(*(row[k] for k in keys),store.stamp()))
        store.audit(c,'master_link',{'before':dict(old) if old else None,'after':row,'reason':payload['reason']})
    return {'saved':True}

@app.get('/api/baseline/{period}')
def baseline_comparison(period:str):
    calculated=closing.preview(period)
    with store.db() as c:
        baselines=[{**dict(r),'meta':json.loads(r['meta'])} for r in c.execute("SELECT * FROM sources WHERE status='reference' ORDER BY id DESC")]
    source=next((s for s in baselines if s['meta'].get('baseline_period')==period),None)
    if not source:return {'rows':[],'message':'해당 월의 기준 마감 엑셀을 등록해주세요'}
    rows=[]
    from decimal import Decimal
    for old in source['meta']['baseline']:
        current=next((r for r in calculated['customers'] if r['customer']==old['customer']),None)
        for key,label in [('opening','전월 이월'),('receipt','당월 입고'),('settlement','당월 정산'),('closing','당월 미결'),('amount','정산 금액(원)')]:
            value=current.get('settlement_amount' if key=='amount' else key) if current else None
            difference=str(Decimal(value)-Decimal(str(old[key]))) if value is not None and old[key] is not None else None
            rows.append({'customer':old['customer'],'항목':label,'기준 값':old[key],'현재 계산':value,'차이':difference,'source_id':source['id']})
    return {'rows':rows,'ready':calculated['ready'],'message':'미해결 자료가 있으면 차이는 잠정값입니다. 출하 배부·단가·이월 원본으로 차이 원인을 확인하세요.'}

@app.post('/api/records')
def manual(payload:dict):
    if not str(payload.get('reason','')).strip():
        raise ValueError('입력·수정 사유를 작성해주세요')
    with LOCK:
        return imports.commit_rows(payload['rows'],None,payload['scope'],payload.get('mode','append'),payload['reason'],payload.get('confirm',False))

@app.post('/api/records/{record_id}/revise')
def revise(record_id:int,payload:dict):
    reason=str(payload.get('reason','')).strip()
    if not reason:raise ValueError('수정 사유가 필요합니다')
    with LOCK:
        with store.db() as c:
            old=c.execute('SELECT r.*,b.scope FROM records r JOIN batches b ON b.id=r.batch_id WHERE r.id=? AND b.active=1',(record_id,)).fetchone()
            if not old:raise ValueError('이미 변경된 데이터입니다. 새로고침해주세요')
            rows=[dict(r) for r in c.execute('SELECT r.* FROM records r JOIN batches b ON b.id=r.batch_id WHERE b.active=1 AND b.scope=?',(old['scope'],))]
        for row in rows:
            row['provenance']=json.loads(row['provenance'])
            if row['id']==record_id:
                row.update({k:v for k,v in payload['row'].items() if k in ('part','customer','date','quantity','price','amount','note')})
                row['provenance']={**row['provenance'],'corrected_record_id':record_id,'reason':reason}
        return imports.commit_rows(rows,None,old['scope'],'replace',reason,True)

@app.get('/api/issues')
def issues():
    with store.db() as c:
        return [dict(r) for r in c.execute('SELECT * FROM issues WHERE resolved=0 ORDER BY id DESC')]

@app.get('/api/closing/{period}')
def preview(period:str):
    with LOCK:
        return closing.preview(period)

@app.post('/api/closing/{period}')
def confirm(period:str,payload:dict):
    with LOCK:
        return closing.finalize(period,payload['fingerprint'])

@app.get('/api/runs')
def runs():
    with store.db() as c:
        return [dict(r) for r in c.execute('SELECT id,period,version,created FROM runs ORDER BY id DESC')]

@app.get('/api/runs/{rid}')
def run_detail(rid:int):
    with store.db() as c:
        row=c.execute('SELECT * FROM runs WHERE id=?',(rid,)).fetchone()
    if not row: raise HTTPException(404)
    return {**dict(row),'snapshot':json.loads(row['snapshot'])}

@app.post('/api/runs/{rid}/export')
def export(rid:int):
    from .reports import generate
    return job(lambda:generate(rid))

@app.get('/api/outputs')
def outputs():
    return [p.name for p in (store.ROOT/'outputs').glob('*') if p.suffix in ('.xlsx','.pptx','.json')]

@app.get('/api/outputs/{name}')
def output(name:str):
    path=(store.ROOT/'outputs'/name).resolve()
    if path.parent!=(store.ROOT/'outputs').resolve() or not path.is_file(): raise HTTPException(404)
    return FileResponse(path,filename=path.name)

@app.get('/api/jobs/{jid}')
def get_job(jid:str):
    with store.db() as c:
        row=c.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
    if not row: raise HTTPException(404)
    return dict(row)

@app.get('/api/backups')
def backups():
    return sorted([p.name for p in (store.ROOT/'backups').glob('*.sqlite3')],reverse=True)

@app.post('/api/backups')
def backup():
    with LOCK: return {'file':store.backup()}

@app.post('/api/restore')
def restore(payload:dict):
    path=(store.ROOT/'backups'/payload['file']).resolve()
    if path.parent!=(store.ROOT/'backups').resolve() or not path.is_file(): raise ValueError('백업 파일을 찾을 수 없습니다')
    with LOCK:
        store.backup()
        check=sqlite3.connect(path)
        try:
            if check.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('백업 파일 검사 실패')
            check.execute('SELECT version FROM schema_version')
            with store.db() as target: check.backup(target)
        finally: check.close()
        store.init()
    return {'restored':True}

assets=(Path(getattr(sys,'_MEIPASS',store.ROOT))/'frontend'/'dist')
if assets.exists():
    app.mount('/',StaticFiles(directory=assets,html=True),name='ui')
