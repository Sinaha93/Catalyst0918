"""Reviewed August-2026 migration, not a recurring closing calculation adapter.

Reads cached source values without modifying workbooks. The existing closing
supplies historical settlements/openings; supplier files independently check
settlements. This is explicitly not proof of end-to-end automated closing.
"""
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
import hashlib
import json
from . import imports, store

PERIOD = '2026-08'
CUSTOMERS = ['기아 화성','기아 광명','기아 광주','현대 아산','현대 울산','현대 전주','현대 글로비스','현대 위아','세종공업','현대 모비스']
ALIASES = {'현대모비스(주)':'현대 모비스','기아(주)-광명':'기아 광명','기아(주)-광주':'기아 광주','기아(주)-화성':'기아 화성','에스제이지세종(주)':'세종공업','현대위아(주)':'현대 위아','현대자동차(주)울산':'현대 울산','현대자동차(주)아산':'현대 아산','현대자동차(주)전주':'현대 전주','현대글로비스(주)':'현대 글로비스','글로비스':'현대 글로비스','현대위아':'현대 위아','현대모비스':'현대 모비스'}
EXCLUDED = {'R600289E0-4A120','R600289E0-4A720'}

def num(value):
    return Decimal(imports.number(value,required=True))

def build(paths):
    """Validate the complete candidate before any business records are written."""
    data={k:imports.tables(Path(p)) for k,p in paths.items()}
    rows=[]; warnings=[]; links={}; master={}; quantities=defaultdict(lambda:defaultdict(Decimal))
    def add(role,sheet,r,kind,part,customer='',**values):
        row={'kind':kind,'part':part,'customer':customer,'date':PERIOD+('-31' if kind in ('receipt','settlement') else '-01'),**values,
             'provenance':{'file':Path(paths[role]).name,'sheet':sheet,'row':r,
                           'migration':'2026-08 reviewed historical bootstrap','role':role,
                           'date_basis':'월 집계 기준일. 실제 개별 입고일을 뜻하지 않음.'}}
        imports.normalize(row)
        rows.append(row)
        if kind in ('receipt','settlement','opening'):
            quantities[(customer,part)][kind]+=num(values['quantity'])
            if part in master:
                links[(part,customer)]={'part':part,'customer':customer,'supplier':master[part]['supplier'],
                    'factory':customer,'vehicle':'','price_type':'',
                    'settlement_counterparty':'전주공장' if part=='28991-4C520' else master[part]['supplier']}

    ms=data['master']['촉매 현황']
    if ms[0][1]!='품번' or ms[0][2]!='촉매사' or not str(ms[0][8]).startswith('단가'):
        raise ValueError('촉매 마스터 열 구조가 변경되었습니다')
    for r,raw in enumerate(ms[1:],2):
        if not raw[1]:continue
        p=str(raw[1]).strip(); price=num(raw[8])
        if p in master and (master[p]['price']!=price or master[p]['supplier']!=raw[2]):
            raise ValueError('마스터 품번 중복·충돌: '+p)
        if p in master:continue
        master[p]={'price':price,'supplier':raw[2]}
        add('master','촉매 현황',r,'part',p)
        add('master','촉매 현황',r,'price',p,price=str(price),note='8월 전체 적용. 8/28은 단가 확인일.')

    book=data['closing']
    total_settled=defaultdict(Decimal)
    for customer in CUSTOMERS:
        table=book[customer]
        if table[7][2:6]!=['품번','매입 단가','수량','금액']:
            raise ValueError('계산서 구조 변경: '+customer)
        if table[1][1]!='8월 촉매 계산서' or table[4][1]!='작성일 : 2026.8.31':
            raise ValueError('이관 기능은 확인된 2026년 8월 자료 전용입니다')
        for r,raw in enumerate(table[8:],9):
            p=raw[2]
            if not isinstance(p,str) or '-' not in p:continue
            q,price,amount=map(num,[raw[4],raw[3],raw[5]])
            if p not in master or price!=master[p]['price'] or q*price!=amount:
                raise ValueError('정산 단가·금액 대사 불일치: '+p)
            add('closing',customer,r,'settlement',p,customer,quantity=str(q),
                note='기존 8월 마감 정산수량 이관'+(' / 전주공장 직사급' if p=='28991-4C520' else ''))
            total_settled[p]+=q

    usheet=next(s for s,rs in book.items() if rs and rs[0] and any('26년 8월 이월 및 정산품목' in str(v) for v in rs[0]))
    expected={}; current_customer=None
    for r,raw in enumerate(book[usheet][3:],4):
        if raw[2] and raw[2]!='소 계':current_customer=ALIASES.get(raw[2],raw[2])
        p=raw[4]
        if not isinstance(p,str) or '-' not in p:continue
        if current_customer not in CUSTOMERS:raise ValueError('이월 거래처 확인 필요')
        q,receipt,settle,balance=map(num,raw[7:11])
        if q+receipt-settle!=balance:raise ValueError('기존 미정산 수량 불일치: '+p)
        key=(current_customer,p)
        if key in expected:raise ValueError('미정산 중복 품번·거래처: '+p)
        expected[key]=balance
        # Opening quantity migration revalues known parts at the user-confirmed
        # August master. Unknown old rates are source evidence, not new master rates.
        price=master[p]['price'] if p in master else num(raw[6])
        add('closing',usheet,r,'opening',p,current_customer,quantity=str(q),amount=str(q*price),
            note=str(raw[12] or '')+' / 기존 마감 이월 수량; 등록 단가 기준 평가')
        if p not in master:warnings.append({'part':p,'customer':current_customer,'message':'마스터 누락. 기존 이월 단가는 참고값으로만 보존','sheet':usheet,'row':r})
    for customer in CUSTOMERS:
        if not any(c==customer for c,_ in expected):
            # No explicit opening detail means zero for this reviewed baseline,
            # only when its independently labeled summary also says zero.
            sr=next(raw for raw in book['종합'][6:16] if raw[2]==customer)
            if num(sr[3])!=0:raise ValueError('이월 상세 누락: '+customer)

    erps=[(s,rs) for s,rs in data['erp'].items() if len(rs)>3 and rs[1][2]=='품번' and rs[2][6]=='수량계']
    if len(erps)!=1:raise ValueError('ERP 입고 시트를 하나로 식별할 수 없습니다')
    es,table=erps[0]
    headers=table[1]; excluded=Decimal(0); erptotal=Decimal(0)
    for r,raw in enumerate(table[4:],5):
        if not raw[2]:continue
        total=num(raw[6]); erptotal+=total
        if total!=sum((num(v) for v in raw[7:17] if v is not None),Decimal(0)):
            raise ValueError('ERP 행 합계 불일치')
        if raw[2] in EXCLUDED:excluded+=total;continue
        p=str(raw[2]); p=p[4:] if p.startswith('R600') else p
        for c in range(7,17):
            q=num(raw[c]) if raw[c] is not None else Decimal(0)
            if not q:continue
            customer=ALIASES.get(headers[c])
            if not customer:raise ValueError('ERP 거래처 미등록: '+str(headers[c]))
            add('erp',es,r,'receipt',p,customer,quantity=str(q))
            rows[-1]['provenance']['column']=c+1
    if erptotal!=num(table[3][6]):raise ValueError('ERP 전체 합계 불일치')

    for key,values in quantities.items():
        if values['opening']+values['receipt']-values['settlement']!=expected.get(key,Decimal(0)):
            raise ValueError('ERP와 기존 마감의 잔량 불일치: '+str(key))
    for role,pc,qc,start in [('umicore',3,18,4),('heesung',1,17,2)]:
        candidates=[(s,rs) for s,rs in data[role].items() if
            (role=='umicore' and s=='납품 Summary') or
            (role=='heesung' and s=='8월 마감자료')]
        if len(candidates)!=1:raise ValueError('촉매사 마감 시트를 확인해주세요')
        sn,table=candidates[0]; check=defaultdict(Decimal)
        for raw in table[start:]:
            p=raw[pc]
            if isinstance(p,str) and '-' in p:check[p]+=num(raw[qc]) if raw[qc] is not None else Decimal(0)
        for p,q in check.items():
            if q!=total_settled[p]:raise ValueError('촉매사 정산 대사 불일치: '+p)
    return {'rows':rows,'links':list(links.values()),'warnings':warnings,'excluded_quantity':str(excluded),
            'record_count':len(rows),'period':PERIOD,'source_paths':{k:str(v) for k,v in paths.items()}}

def apply(paths):
    result=build(paths)
    hashes={k:hashlib.sha256(Path(p).read_bytes()).hexdigest() for k,p in paths.items()}
    fingerprint=hashlib.sha256(store.encode(hashes).encode()).hexdigest()
    scope='reviewed-august-bootstrap:'+fingerprint
    with store.db() as c:
        if c.execute('SELECT 1 FROM batches WHERE scope=? AND active=1',(scope,)).fetchone():
            return {'duplicate':True,'period':PERIOD}
        if c.execute('SELECT 1 FROM batches WHERE active=1').fetchone() or c.execute('SELECT 1 FROM runs').fetchone():
            raise ValueError('초기 이관은 거래/확정 마감이 없는 저장소에서만 가능합니다. 기존 자료를 덮어쓰지 않습니다.')
    backup=store.backup()
    # Registration retains originals. It must not auto-apply saved profiles.
    with store.db() as c:
        if c.execute('SELECT 1 FROM profiles').fetchone():raise ValueError('저장된 양식이 있는 저장소에서는 수동 이관 검토가 필요합니다')
    sources={k:imports.register(p)['id'] for k,p in paths.items()}
    with store.db() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM batches WHERE active=1').fetchone() or c.execute('SELECT 1 FROM runs').fetchone():raise ValueError('자료가 변경되었습니다. 다시 확인해주세요')
        bids={}
        for role in ('master','closing','erp'):
            bids[role]=c.execute('INSERT INTO batches(source_id,scope,mode,created) VALUES(?,?,?,?)',
                (sources[role],scope,'append',store.stamp())).lastrowid
        for raw in result['rows']:
            row=imports.normalize(raw); prov={**raw['provenance'],'source_id':sources[raw['provenance']['role']]}
            c.execute('INSERT INTO records(batch_id,kind,part,customer,date,quantity,price,amount,note,provenance) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (bids[prov['role']],*(row[k] for k in ('kind','part','customer','date','quantity','price','amount','note')),store.encode(prov)))
        for row in result['links']:
            # Never overwrite user-maintained links.
            c.execute('INSERT OR IGNORE INTO part_links(part,customer,factory,supplier,vehicle,price_type,updated) VALUES(?,?,?,?,?,?,?)',
                (*(row[k] for k in ('part','customer','factory','supplier','vehicle','price_type')),store.stamp()))
        for role in ('master','erp'):
            c.execute("UPDATE sources SET status='imported' WHERE id=?",(sources[role],))
        for role in ('umicore','heesung'):
            c.execute("UPDATE sources SET status='reference' WHERE id=?",(sources[role],))
        store.audit(c,'reviewed_august_bootstrap',{'hashes':hashes,'sources':sources,'warnings':result['warnings'],
            'backup':backup,'record_count':len(result['rows']),'note':'기존 마감 수량 이관; 마감 자동화 완성 검증 아님'})
    return {k:v for k,v in result.items() if k not in ('rows','links')}|{'backup':backup,'duplicate':False}
