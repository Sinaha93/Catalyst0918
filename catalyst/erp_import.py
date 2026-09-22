"""Monthly ERP crosstab import. Reporting month is explicitly selected, never inferred."""
import calendar
import hashlib
import json
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal
from . import imports, store
from .august_bootstrap import ALIASES, EXCLUDED

TYPE='ERP 월 입고현황'


def is_layout(rows):
    return (len(rows)>=3 and len(rows[0])>=1 and len(rows[1])>=8 and len(rows[2])>=8
            and str(rows[0][0] or '').strip()=='기간별구매거래처입고현황'
            and rows[1][2]=='품번' and rows[1][6]=='합계' and rows[2][6]=='수량계')


def recognizes_meta(meta):
    for sheet in meta.get('sheets',[]):
        headers={h['row']:h['cells'] for h in sheet.get('headers',[])}
        if is_layout([headers.get(i,[]) for i in (1,2,3)]):return True
    return False


def parse(data,period,provenance):
    if not re.fullmatch(r'\d{4}-\d{2}',str(period or '')):raise ValueError('대상 월을 선택해주세요')
    start=date.fromisoformat(period+'-01')
    effective=date(start.year,start.month,calendar.monthrange(start.year,start.month)[1]).isoformat()
    matches=[(s,rows) for s,rows in data.items() if is_layout(rows)]
    if len(matches)!=1:raise ValueError('ERP 월 입고 양식을 하나로 식별할 수 없습니다')
    sheet,table=matches[0]
    if len(table)<5 or table[3][0]!='TOTAL':raise ValueError('ERP TOTAL 행 또는 품목 자료가 없습니다')
    headers=table[1]; subheaders=table[2]; columns=[]; seen=set()
    for col in range(7,len(headers)):
        label=str(headers[col] or '').strip()
        if not label:raise ValueError(f'{sheet} {col+1}열 거래처 제목이 없습니다')
        if col>=len(subheaders) or subheaders[col]!='수량':raise ValueError('거래처별 수량 열 구조가 변경되었습니다')
        customer=ALIASES.get(label)
        if not customer:raise ValueError('ERP 거래처 연결 필요: '+label)
        if customer in seen:raise ValueError('ERP 거래처 열 중복: '+customer)
        seen.add(customer);columns.append((col,customer))
    def num(value,required=False):return Decimal(imports.number(value,required) or '0')
    totals=defaultdict(Decimal); expected=defaultdict(Decimal); rows=[];excluded=[];grand=Decimal(0)
    for index,raw in enumerate(table[4:],5):
        if all(v is None or str(v).strip()=='' for v in raw):continue
        if len(raw)<len(headers) or not raw[2]:raise ValueError(f'{sheet} {index}행 품번 또는 수량 열 누락')
        p=str(raw[2]).strip(); normalized=p[4:] if p.startswith('R600') else p
        q=num(raw[6],True)
        values=[(col,customer,num(raw[col])) for col,customer in columns]
        if sum((v for _,_,v in values),Decimal(0))!=q:raise ValueError(f'{sheet} {index}행 전체 수량과 거래처별 합계가 다릅니다')
        if str(raw[4]).strip().upper()!='EA' or str(raw[5]).strip().upper()!='KRW':raise ValueError(f'{sheet} {index}행 단위·통화 확인 필요(EA/KRW)')
        grand+=q
        for col,customer,v in values:expected[customer]+=v
        if p in EXCLUDED or 'R600'+normalized in EXCLUDED:
            excluded.append({'part':p,'quantity':str(q),'row':index});continue
        if str(raw[1]).strip().upper() not in {'CATALYST','CATALYST-FR','CATALYST-RR','CATALYST-GPF','CATALYST GPF'}:
            raise ValueError(f'{sheet} {index}행 촉매 외 품목 확인 필요: {raw[1]} / {p}')
        for col,customer,v in values:
            if not v:continue
            if v<0:raise ValueError(f'{sheet} {index}행 음수 입고는 반품·조정 사유를 확인해주세요')
            totals[customer]+=v
            rows.append({'kind':'receipt','part':normalized,'customer':customer,'date':effective,'quantity':str(v),
                         'provenance':{**provenance,'sheet':sheet,'row':index,'column':col+1,'original_part':p,
                                       'reporting_period':period,'date_basis':'월 집계 기준일이며 실제 개별 입고일이 아닙니다'}})
    if grand!=num(table[3][6],True):raise ValueError('ERP TOTAL 전체 수량 대사가 맞지 않습니다')
    for col,customer in columns:
        if expected[customer]!=num(table[3][col],True):raise ValueError('ERP TOTAL 거래처 수량 대사가 맞지 않습니다: '+customer)
    if not rows:raise ValueError('반영할 촉매 입고 수량이 없습니다')
    return {'period':period,'date':effective,'rows':rows,'count':len(rows),'parts':len({r['part'] for r in rows}),
            'total':str(grand),'excluded':excluded,'excluded_total':str(sum((Decimal(r['quantity']) for r in excluded),Decimal(0))),
            'receipt_total':str(sum(totals.values(),Decimal(0))),'customers':[{'customer':c,'quantity':str(q)} for c,q in totals.items()]}


def preview(sid,period):
    with store.db() as c:
        source=c.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
        if not source or source['status'] in ('deleted','cancelled'):raise ValueError('사용할 ERP 등록 자료를 선택해주세요')
        active=[dict(r) for r in c.execute("SELECT b.id,b.scope,b.source_id,r.date FROM records r JOIN batches b ON b.id=r.batch_id WHERE b.active=1 AND r.kind='receipt'")]
        revision=c.execute('SELECT COALESCE(MAX(id),0) FROM audit').fetchone()[0]
    path=imports.source_path(source)
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=source['hash']:raise ValueError('보관 원본이 없거나 변경되었습니다. 원본을 다시 확인해주세요')
    result=parse(imports.tables(path),period,{'source_id':sid,'file':source['name']})
    scope='erp-monthly-receipt:'+period
    current=[r for r in active if r['date'].startswith(period)]
    result['errors']=[]
    if any(r['source_id']==sid for r in active):result['errors'].append('이미 반영된 파일입니다. 수정본을 새로 등록해주세요.')
    if any(r['scope']!=scope for r in current):result['errors'].append('선택 월에 다른 자료 묶음 또는 직접 입력 입고가 있습니다. 중복 방지를 위해 먼저 확인해주세요.')
    result['replace_count']=sum(r['scope']==scope for r in current)
    result['scope']=scope
    result['fingerprint']=hashlib.sha256((store.encode(result)+str(revision)).encode()).hexdigest()
    return result


def apply(sid,payload):
    result=preview(sid,payload.get('period'))
    if result['errors']:raise ValueError(' / '.join(result['errors']))
    if payload.get('fingerprint')!=result['fingerprint']:raise ValueError('자료가 변경되었습니다. 다시 미리보기해주세요')
    if payload.get('confirm_period') is not True:raise ValueError('ERP 조회 대상 월이 선택한 월과 일치하는지 확인해주세요')
    backup=store.backup()
    saved=imports.commit_rows(result['rows'],sid,result['scope'],'replace','ERP 월 입고 전용 등록: '+result['period'])
    return {**saved,'period':result['period'],'backup':backup,'quantity':result['receipt_total']}
