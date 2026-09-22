"""Dated monthly plan export: exact headers, no manual column mapping."""
import hashlib
from collections import defaultdict
from decimal import Decimal as D
from . import imports, store
from .august_bootstrap import CUSTOMERS

TYPE='월계획 등록 자료'
HEADERS=['일자','품번','거래처','수량','단가(원)','금액(원)','비고']

def matches(data):
    return [(s,rs) for s,rs in data.items() if s.strip()=='계획' and rs and rs[0][:7]==HEADERS and all(v in (None,'') for v in rs[0][7:])]

def recognizes_meta(meta):
    return sum(s.get('name','').strip()=='계획' and any(h['row']==1 and h['cells'][:7]==HEADERS and all(v in (None,'') for v in h['cells'][7:]) for h in s.get('headers',[])) for s in meta.get('sheets',[]))==1

def parse(data,provenance):
    found=matches(data)
    if len(found)!=1:raise ValueError('월계획 표를 하나로 확인할 수 없습니다')
    sheet,table=found[0];rows=[];seen=set();totals=defaultdict(lambda:{'quantity':D(0),'amount':D(0)})
    for i,raw in enumerate(table[1:],2):
        if all(v in (None,'') for v in raw):continue
        if len(raw)<6:raise ValueError(f'{sheet} {i}행: 필수 열이 없습니다')
        if any(v not in (None,'') for v in raw[7:]):raise ValueError(f'{sheet} {i}행: 제목 없는 추가 열이 있습니다')
        row={'kind':'plan','date':raw[0],'part':raw[1],'customer':raw[2],'quantity':raw[3],'price':raw[4],'amount':raw[5],'note':raw[6] if len(raw)>6 else ''}
        try:
            r=imports.normalize(row)
            if r['customer'] not in CUSTOMERS:raise ValueError('납품처 확인 필요: '+r['customer'])
            q=D(r['quantity']);price=D(imports.number(raw[4],True));amount=D(imports.number(raw[5],True))
            if q<0 or q!=q.to_integral_value():raise ValueError('계획 수량은 0 이상의 정수여야 합니다')
            if q*price!=amount:raise ValueError('수량 × 단가와 금액이 다릅니다')
            key=(r['part'],r['customer'])
            if key in seen:raise ValueError('동일 품번·납품처가 중복되어 있습니다')
            seen.add(key)
        except (ValueError,TypeError) as e:raise ValueError(f'{sheet} {i}행: {e}')
        r['provenance']={**provenance,'sheet':sheet,'row':i,'adapter':'monthly-plan'}
        rows.append(r);totals[r['customer']]['quantity']+=q;totals[r['customer']]['amount']+=amount
    months={r['date'][:7] for r in rows}
    if len(months)!=1:raise ValueError('계획 자료는 한 달씩 등록해주세요. 날짜가 없거나 여러 월이 섞여 있습니다.')
    return {'period':next(iter(months)),'rows':rows,'count':len(rows),'quantity':str(sum((r['quantity'] for r in totals.values()),D(0))),
            'amount':str(sum((r['amount'] for r in totals.values()),D(0))),'customers':[{'customer':c,**{k:str(v) for k,v in r.items()}} for c,r in totals.items()]}

def preview(sid):
    with store.db() as c:
        source=c.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
        if not source or source['status'] in ('deleted','cancelled'):raise ValueError('사용할 월계획 자료를 선택해주세요')
        path=imports.source_path(source)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=source['hash']:raise ValueError('보관 원본이 없거나 변경되었습니다')
        result=parse(imports.tables(path),{'source_id':sid,'file':source['name']})
        scope='monthly-plan:'+result['period'];result['scope']=scope;result['errors']=[]
        current=[dict(r) for r in c.execute("SELECT b.source_id,b.scope FROM records r JOIN batches b ON b.id=r.batch_id WHERE b.active=1 AND r.kind='plan' AND substr(r.date,1,7)=?",(result['period'],))]
        if any(r['scope']!=scope for r in current):result['errors'].append('이 월에 직접 입력 또는 다른 방식의 계획이 있습니다. 기존 계획을 확인해주세요.')
        if c.execute('SELECT 1 FROM batches WHERE source_id=? AND active=1',(sid,)).fetchone():result['errors'].append('이미 반영된 파일입니다. 수정본을 새로 등록해주세요.')
        result['replace_count']=len(current)
        revision=c.execute('SELECT COALESCE(MAX(id),0) FROM audit').fetchone()[0]
    result['fingerprint']=hashlib.sha256((store.encode(result)+str(revision)).encode()).hexdigest()
    return result

def apply(sid,payload):
    result=preview(sid)
    if result['errors']:raise ValueError(' / '.join(result['errors']))
    if payload.get('fingerprint')!=result['fingerprint']:raise ValueError('자료가 변경되었습니다. 다시 확인해주세요')
    store.backup()
    saved=imports.commit_rows(result['rows'],sid,result['scope'],'replace','파일 일자 기준 월계획 자동 연결: '+result['period'])
    return {**saved,'period':result['period'],'quantity':result['quantity'],'amount':result['amount']}
