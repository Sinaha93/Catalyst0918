"""Import adapters preserve source rows. Unknown layouts require an explicit mapping."""
import csv
import hashlib
import io
import json
import re
import shutil
import zipfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import openpyxl
from . import store

KINDS = {'part','price','receipt','shipment','settlement','opening','plan','adjustment'}

def source_path(source):
    return store.ROOT/'archive'/(source['hash']+Path(source['path']).suffix)

def number(value, required=False):
    if value is None or str(value).strip() == '':
        if required:
            raise ValueError('필수 숫자가 비어 있습니다')
        return None
    try:
        result = Decimal(str(value).replace(',', '').strip())
        if not result.is_finite():
            raise ValueError('유한한 숫자가 필요합니다')
        return str(result)
    except InvalidOperation:
        raise ValueError(f'숫자 형식 오류: {value}')

def day(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return date.fromisoformat(str(value).strip()[:10]).isoformat()

def normalize(row):
    kind = row.get('kind', '')
    if kind not in KINDS:
        raise ValueError('자료 구분을 선택해주세요')
    result = {key: str(row.get(key) or '').strip() for key in ('part','customer','note')}
    result.update(kind=kind, date=day(row.get('date')))
    if not result['part']:
        raise ValueError('품번이 필요합니다')
    if kind not in ('part','price') and not result['customer']:
        raise ValueError('거래처가 필요합니다')
    for key in ('quantity','price','amount'):
        required = (key == 'price' and kind == 'price') or (key == 'quantity' and kind not in ('part','price'))
        result[key] = number(row.get(key), required)
    if result['price'] is not None and Decimal(result['price']) < 0:
        raise ValueError('단가는 음수일 수 없습니다')
    return result

def tables(path):
    if path.suffix.lower() == '.csv':
        raw = path.read_bytes()
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = raw.decode('cp949')
        return {'CSV': list(csv.reader(io.StringIO(text)))}
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        return {ws.title: [list(row) for row in ws.iter_rows(values_only=True)] for ws in wb}
    finally:
        wb.close()

def signature(headers):
    return hashlib.sha256(store.encode([str(h or '').strip() for h in headers]).encode()).hexdigest()

def inspect(path):
    suffix = path.suffix.lower()
    if suffix == '.pptx':
        with zipfile.ZipFile(path) as z:
            return {'type':'보고서 기준자료','slides':len([n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+.xml',n)]),'sheets':[]}
    if suffix not in ('.xlsx','.csv'):
        raise ValueError('xlsx, csv, pptx 파일을 지원합니다. 구형 xls는 xlsx로 저장해주세요.')
    data = tables(path)
    from .master_import import identify
    from .erp_import import is_layout, TYPE
    kind = identify(data) or '열 연결 필요'
    if any(is_layout(rows) for rows in data.values()):kind=TYPE
    if '종합' in data and any(name in data for name in ('월별 계획·실적','종합2')):
        kind = '월마감 기준자료'
    elif '납품 Summary' in data:
        kind = '주차별 발주납품'
    elif '글로비스' in data and 'Sheet2' in data:
        kind = '출하 배부자료'
    from .supplier_import import identify as supplier_type
    kind = supplier_type(data) or kind
    from .plan_import import matches, TYPE as PLAN_TYPE
    if len(matches(data))==1:kind=PLAN_TYPE
    sheets = []
    for name, rows in data.items():
        candidates = []
        for index, row in enumerate(rows[:40]):
            if any(v is not None for v in row):
                candidates.append({'row':index+1,'cells':[str(v or '') for v in row[:80]],'signature':signature(row)})
        sheets.append({'name':name,'rows':len(rows),'headers':candidates,'sample':rows[:8]})
    meta = {'type':kind,'sheets':sheets}
    if kind == '월마감 기준자료':
        summary = data['종합']
        meta['baseline'] = [{'customer':r[2], 'opening':r[3], 'receipt':r[5], 'settlement':r[7], 'closing':r[9], 'amount':r[8]} for r in summary[6:16]]
        meta['baseline_period'] = '2026-08' if '26년 8월' in path.name else None
    if suffix == '.xlsx':
        with zipfile.ZipFile(path) as z:
            meta['external_links'] = len([n for n in z.namelist() if re.fullmatch(r'xl/externalLinks/externalLink\d+.xml',n)])
    return meta

def register(path, allow_deleted=False):
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with store.db() as c:
        existing = c.execute('SELECT id,status FROM sources WHERE hash=?',(digest,)).fetchone()
        if existing and not (allow_deleted and existing['status']=='deleted'):
            return {**dict(existing),'duplicate':True}
    destination = store.ROOT / 'archive' / (digest + path.suffix.lower())
    if not destination.exists():
        shutil.copy2(path,destination)
    try:
        meta = inspect(path)
        status = 'reference' if '기준자료' in meta['type'] else 'pending'
    except Exception as e:
        meta, status = {'type':'읽기 오류','error':str(e),'sheets':[]}, 'error'
    meta['registered_from']=str(path.resolve())
    meta['registered_from_kind']='input' if path.resolve().parent==(store.ROOT/'input').resolve() else 'file'
    if existing:meta['reimport_allowed']=True
    with store.db() as c:
        if existing:
            c.execute('UPDATE sources SET name=?,path=?,status=?,meta=?,created=? WHERE id=?',(path.name,str(destination),status,store.encode(meta),store.stamp(),existing['id']))
        else:
            c.execute('INSERT OR IGNORE INTO sources(name,hash,path,status,meta,created) VALUES(?,?,?,?,?,?)', (path.name,digest,str(destination),status,store.encode(meta),store.stamp()))
        sid = c.execute('SELECT id FROM sources WHERE hash=?',(digest,)).fetchone()[0]
        store.audit(c,'register',{'source_id':sid,'name':path.name})
    if status == 'pending':
        auto_apply(sid,meta)
    return {'id':sid,'duplicate':False}

def auto_apply(sid,meta):
    from . import plan_import
    if meta.get('type')==plan_import.TYPE:
        try:
            result=plan_import.preview(sid)
            # Revisions or manual plans require visible confirmation; new months do not.
            if not result['errors'] and not result['replace_count']:plan_import.apply(sid,result)
        except (ValueError,TypeError):pass
        return
    from .erp_import import TYPE
    if meta.get('type')==TYPE:return  # Monthly crosstabs have no transaction date column.
    from .supplier_import import meta_type
    if meta_type(meta):return  # Supplier receipts must not duplicate the ERP ledger.
    with store.db() as c:
        profiles = [json.loads(r[0]) for r in c.execute('SELECT config FROM profiles')]
    matches = [p for p in profiles if any(s['name']==p['sheet'] and any(h['row']==p['header_row'] and h['signature']==p['signature'] for h in s['headers']) for s in meta['sheets'])]
    # A default date is specific to the reviewed file, not a safe recurring rule.
    matches=[p for p in matches if p.get('columns',{}).get('date') not in (None,'')]
    if len(matches) == 1:
        try:
            apply(sid,matches[0],save_profile=False)
        except ValueError:
            pass

def commit_rows(rows, source_id, scope, mode, reason='', confirm=False):
    if mode not in ('append','replace') or not scope.strip():
        raise ValueError('추가/교체 방식과 자료 묶음 이름이 필요합니다')
    normalized = []
    for i,row in enumerate(rows):
        try:
            normalized.append((normalize(row),row.get('provenance',{'row':i+1,'reason':reason})))
        except (ValueError,TypeError) as e:
            raise ValueError(f'{i+1}번째 자료: {e}')
    if not normalized:
        raise ValueError('반영할 자료가 없습니다')
    with store.db() as c:
        # A source hash is imported at most once unless explicitly revised via a new source.
        if source_id:
            source=c.execute('SELECT status,meta FROM sources WHERE id=?',(source_id,)).fetchone()
            if not source or source['status'] in ('cancelled','deleted'):
                raise ValueError('삭제·취소한 자료는 반영할 수 없습니다')
        if source_id and c.execute('SELECT 1 FROM batches WHERE source_id=?',(source_id,)).fetchone():
            if source['status']=='imported' or not json.loads(source['meta']).get('reimport_allowed') or c.execute('SELECT 1 FROM batches WHERE source_id=? AND active=1',(source_id,)).fetchone():
                raise ValueError('이미 반영된 파일입니다. 수정본을 새로 등록해주세요.')
        old = c.execute('SELECT id FROM batches WHERE scope=? AND active=1',(scope,)).fetchall()
        # Manual and conflicting price revisions require a visible decision.
        conflicts=[]
        seen_prices={}
        for row,_ in normalized:
            if row['kind']=='price':
                key=(row['part'],row['customer'],row['date'])
                if key in seen_prices and Decimal(seen_prices[key])!=Decimal(row['price']):
                    raise ValueError('한 자료 안에 서로 다른 적용 단가가 있습니다')
                seen_prices[key]=row['price']
                existing=c.execute('SELECT r.price,b.scope FROM records r JOIN batches b ON b.id=r.batch_id WHERE b.active=1 AND r.kind=? AND r.part=? AND r.customer=? AND r.date=?',('price',row['part'],row['customer'],row['date'])).fetchall()
                conflicts.extend([dict(r) for r in existing if Decimal(r['price'])!=Decimal(row['price']) and not (mode=='replace' and r['scope']==scope)])
        if conflicts:
            raise ValueError('같은 품번·거래처·적용일의 단가가 충돌합니다. 기존 자료 묶음을 교체하거나 적용일을 수정해주세요.')
        if mode=='replace' and old:
            manual = c.execute('SELECT 1 FROM batches WHERE scope=? AND active=1 AND source_id IS NULL',(scope,)).fetchone()
            if manual and not confirm:
                raise ValueError('직접 입력값과 충돌합니다. 변경 내용을 확인한 후 수동 교체해주세요.')
            c.execute('UPDATE batches SET active=0 WHERE scope=?',(scope,))
        bid=c.execute('INSERT INTO batches(source_id,scope,mode,created) VALUES(?,?,?,?)',(source_id,scope,mode,store.stamp())).lastrowid
        for row,prov in normalized:
            c.execute('INSERT INTO records(batch_id,kind,part,customer,date,quantity,price,amount,note,provenance) VALUES(?,?,?,?,?,?,?,?,?,?)',(bid,row['kind'],row['part'],row['customer'],row['date'],row['quantity'],row['price'],row['amount'],row['note'],store.encode(prov)))
        if source_id:
            c.execute("UPDATE sources SET status='imported' WHERE id=?",(source_id,))
            c.execute('UPDATE issues SET resolved=1 WHERE source_id=?',(source_id,))
        store.audit(c,'import',{'batch':bid,'count':len(rows),'scope':scope,'mode':mode,'reason':reason})
    return {'batch_id':bid,'count':len(rows)}

def mapped_rows(sid,config):
    with store.db() as c:
        source=c.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
    if not source:
        raise ValueError('원본을 찾을 수 없습니다')
    if source['status'] in ('cancelled','deleted'):
        raise ValueError('삭제·취소한 자료는 반영할 수 없습니다')
    data=tables(source_path(source))
    from .plan_import import matches
    if matches(data):raise ValueError('월계획 전용 등록을 사용해주세요. 날짜·품번·납품처·수량을 자동 연결합니다.')
    from .supplier_import import identify as supplier_type
    if supplier_type(data):
        raise ValueError('이 파일은 촉매사 마감자료입니다. 열 연결 대신 마감자료 등록에서 월만 선택해주세요.')
    from .erp_import import is_layout
    if any(is_layout(rows) for rows in data.values()):
        raise ValueError('ERP 월 입고 전용 등록을 사용해주세요. 전체 합계와 거래처별 수량을 일반 열 연결로 중복 반영할 수 없습니다.')
    sheet=config['sheet']
    header=int(config['header_row'])
    if sheet not in data or header<1 or header>len(data[sheet]):
        raise ValueError('시트 또는 제목 행을 확인해주세요')
    rows=data[sheet]
    result=[]
    for idx,raw in enumerate(rows[header:],header+1):
        if all(v is None or str(v).strip()=='' for v in raw):
            continue
        row=dict(config.get('defaults',{}))
        for field,col in config['columns'].items():
            if col is not None and col!='':
                column=int(col)
                row[field]=raw[column] if column<len(raw) else None
        row['kind']=config['kind']
        row['provenance']={'file':source['name'],'source_id':sid,'sheet':sheet,'row':idx}
        result.append(row)
    return result,signature(rows[header-1])

def apply(sid,config,save_profile=True):
    try:
        rows,sig=mapped_rows(sid,config)
        # Scope includes the data month for monthly transaction imports.
        months=sorted({day(r.get('date'))[:7] for r in rows})
        if config['mode']=='replace' and config['kind'] not in ('part','price') and len(months)>1:
            raise ValueError('교체 자료는 월별로 나누어 등록해주세요. 여러 월을 묶으면 기존 자료와 중복될 수 있습니다.')
        scope=config['scope']
        if config['kind'] not in ('part','price'):
            scope += ':' + ','.join(months)
        result=commit_rows(rows,sid,scope,config['mode'])
        if save_profile:
            config={**config,'signature':sig}
            with store.db() as c:
                for old in c.execute('SELECT id,config FROM profiles').fetchall():
                    p=json.loads(old['config'])
                    if all(p.get(k)==config.get(k) for k in ('sheet','header_row','signature','kind','scope')):
                        c.execute('DELETE FROM profiles WHERE id=?',(old['id'],))
                c.execute('INSERT INTO profiles(name,signature,config) VALUES(?,?,?)',(config.get('name',scope),sig,store.encode(config)))
        return result
    except (ValueError,KeyError,TypeError) as e:
        with store.db() as c:
            c.execute('INSERT INTO issues(source_id,code,message,detail,created) VALUES(?,?,?,?,?)',(sid,'import',str(e),store.encode(config),store.stamp()))
        raise ValueError(str(e))
