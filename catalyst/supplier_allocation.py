"""Derive closing inputs from registered evidence, without changing the receipt ledger."""
import calendar
import hashlib
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal as D
from . import imports, store, supplier_import
from .august_bootstrap import CUSTOMERS

def effective_candidates(part,records,links):
    bom=[r for r in records if r['kind']=='part' and r['part']==part and json.loads(r.get('provenance') or '{}').get('link')]
    if not bom:return {r['customer'] for r in links if r['part']==part and r['customer']}
    latest=max((r['date'],r.get('imported_at','')) for r in bom)
    return {r['customer'] for r in bom if (r['date'],r.get('imported_at',''))==latest and r['customer']} | {
        r['customer'] for r in links if r['part']==part and r['customer'] and r.get('updated','')>latest[1]}


def derive(period,records,links,prior):
    start=date.fromisoformat(period+'-01')
    end=date(start.year,start.month,calendar.monthrange(start.year,start.month)[1]).isoformat()
    with store.db() as c:
        rules={r['part']:dict(r) for r in c.execute('SELECT * FROM part_rules WHERE period=? AND enabled=1',(period,))}
        sources=[dict(r) for r in c.execute("SELECT * FROM sources WHERE status NOT IN ('deleted','cancelled')")
                 if (lambda x:x.get('active') and x.get('period')==period)(json.loads(r['meta']).get('supplier_registration',{}))]
    parsed=[];issues=[];pending=[];rows=[];entries=[];covered=set();owners=defaultdict(set)
    for source in sources:
        try:
            path=imports.source_path(source)
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=source['hash']:raise ValueError('보관 원본 누락 또는 변경')
            result=supplier_import.parse(imports.tables(path),period)
            parsed.append((source,result))
            for item in result['items']:owners[item['part']].add(source['id'])
        except (ValueError,OSError) as e:
            issues.append({'code':'supplier_source','message':source['name']+': '+str(e),'evidence':{'source_id':source['id']}})
    current=[r for r in records if r['date'].startswith(period)]
    full_erp=any(r['kind']=='receipt' and r.get('scope')=='erp-monthly-receipt:'+period for r in current)
    for source,result in parsed:
        groups={}
        for raw in result['items']:
            item=groups.setdefault(raw['part'],{'part':raw['part'],'opening':D(0),'settlement':D(0),'delivery':D(0),'closing':D(0),'allocation':defaultdict(D),'remarks':defaultdict(D),'remark_complete':True,'evidence':[]})
            item['opening']+=D(raw['opening']);item['settlement']+=D(raw['settlement'])
            item['delivery']+=D(raw['delivery']);item['closing']+=D(raw['closing'])
            if raw.get('settlement_allocation') is not None:
                for customer,q in raw['settlement_allocation'].items():item['allocation'][customer]+=D(q)
            if raw.get('remark_allocation') is None:item['remark_complete']=False
            else:
                for customer,q in raw['remark_allocation'].items():item['remarks'][customer]+=D(q)
            item['evidence'].append({'sheet':raw['sheet'],'row':raw['row'],'remark':raw.get('remark','')})
        overrides=json.loads(source['meta']).get('supplier_allocations',{})
        for part,item in groups.items():
            covered.add(part)
            candidates=effective_candidates(part,records,links)
            if part=='28991-4C520':candidates={'현대 전주'}
            receipts={r['customer'] for r in current if r['kind']=='receipt' and r['part']==part}
            receipt_qty=defaultdict(D)
            for r in current:
                if r['part']==part and r['kind']=='receipt':receipt_qty[r['customer']]+=D(r['quantity'])
            complete_receipts=(bool(receipt_qty) or full_erp) and sum(receipt_qty.values(),D(0))==item['delivery'] and all(q>=0 for q in receipt_qty.values()) and not any(r['part']==part and r['kind']=='adjustment' for r in current)
            remark_exact=item['remark_complete'] and complete_receipts and item['delivery']==item['settlement'] and dict(item['remarks'])==dict(receipt_qty)
            for kind in ('opening','settlement'):
                total=item[kind];allocation=None;basis='';reason=''
                existing=[r for r in current if r['part']==part and r['kind']==kind]
                prior_rows=[r for r in (prior or {}).get('details',[]) if r['part']==part]
                saved=overrides.get(part,{}).get(kind)
                if len(owners[part])>1:
                    reason='두 촉매사 자료에 같은 품번이 있습니다. 자료의 품번 범위를 확인해주세요.'
                elif kind=='opening' and prior is not None:
                    # Frozen carry-forward retains its original amount, never repriced.
                    effective={r['customer']:D(r['closing']) for r in prior_rows}
                    manual=defaultdict(D)
                    for r in existing:manual[r['customer']]+=D(r['quantity'])
                    effective.update(manual)
                    qty=sum(effective.values(),D(0))
                    if qty==total:continue
                    reason='전월 확정 이월(또는 직접 입력 이월)과 촉매사 이월 합계가 다릅니다. 기존 이월을 먼저 확인해주세요.'
                elif existing:
                    actual=defaultdict(D)
                    for r in existing:actual[r['customer']]+=D(r['quantity'])
                    native=item['allocation'] if result['supplier']=='heesung' else item['remarks'] if remark_exact else None
                    same_native=kind!='settlement' or native is None or {k:v for k,v in actual.items() if v}=={k:v for k,v in native.items() if v}
                    if sum(actual.values(),D(0))==total and same_native:continue
                    reason='이미 입력한 수량과 촉매사 합계가 다릅니다. 기존 입력을 먼저 확인해주세요.'
                elif saved:
                    allocation={k:D(v) for k,v in saved['values'].items()};basis='사용자 배부 확인: '+saved['reason']
                    if sum(allocation.values(),D(0))!=total:allocation=None;reason='확인한 배부와 원본 합계가 달라졌습니다.'
                elif part in rules:
                    allocation={rules[part]['customer']:total};basis='월별 품번 예외: '+rules[part]['reason']
                elif kind=='settlement' and result['supplier']=='heesung':
                    allocation=dict(item['allocation']);basis='촉매사 원본 납품처별 수량'
                elif kind=='settlement' and remark_exact:
                    allocation=dict(item['remarks']);basis='원본 비고 배부 수량 = ERP 납품처별 입고 = 당월 정산'
                elif kind=='settlement' and item['remark_complete']:
                    reason='비고 배부 수량과 ERP 입고·당월 정산이 일치하지 않아 확인이 필요합니다.'
                elif kind=='settlement' and item['opening']==0 and item['closing']==0 and complete_receipts:
                    allocation=dict(receipt_qty);basis='이월·잔량 0, ERP 전량 정산 일치'
                elif kind=='opening' and item['closing']==0 and complete_receipts and result['supplier']=='heesung' and all(item['allocation'].get(c,D(0))-receipt_qty.get(c,D(0))>=0 for c in set(receipt_qty)|set(item['allocation'])):
                    allocation={c:item['allocation'].get(c,D(0))-receipt_qty.get(c,D(0)) for c in set(receipt_qty)|set(item['allocation'])};basis='잔량 0, 원본 납품처 정산 − ERP 입고'
                elif len(candidates)==1:
                    allocation={next(iter(candidates)):total};basis='단일 BOM 납품처' if part!='28991-4C520' else '확인된 전주공장 직사급'
                elif total==0:
                    customers=candidates|receipts|set(item['allocation'])
                    allocation={customer:D(0) for customer in customers};basis='원본에 명시된 이월·정산 0'
                else:reason='납품처가 여러 곳이거나 BOM 연결이 없습니다. 아래에서 납품처별 수량만 확인해주세요.'
                if allocation is None:
                    entry={'source_id':source['id'],'file':source['name'],'part':part,'kind':kind,'total':str(total),
                           'candidates':sorted(candidates|receipts|set(item['allocation'])),'message':reason,
                           'editable':not existing and not (kind=='opening' and prior is not None) and len(owners[part])==1}
                    pending.append(entry)
                    entries.append(entry)
                    issues.append({'code':'supplier_allocation','message':part+' '+('이월' if kind=='opening' else '정산')+': '+reason,'evidence':entry})
                    continue
                if sum(allocation.values(),D(0))!=total:raise ValueError('배부 합계 검증 실패: '+part)
                entries.append({'source_id':source['id'],'file':source['name'],'part':part,'kind':kind,'total':str(total),'candidates':sorted(allocation),'values':{k:str(v) for k,v in allocation.items()},'message':basis,'editable':True})
                for customer,q in sorted(allocation.items()):
                    rows.append({'id':f'supplier:{source["id"]}:{part}:{kind}:{customer}','source_id':source['id'],
                                 'scope':'supplier-derived:'+period,'kind':kind,'part':part,'customer':customer,
                                 'date':period+'-01' if kind=='opening' else end,'quantity':str(q),'price':None,'amount':None,
                                 'note':'','provenance':store.encode({'source_id':source['id'],'file':source['name'],'rows':item['evidence'],
                                     'allocation_basis':basis,'derived_supplier':True,'date_basis':'월 집계 기준일'})})
    # A supplier file cannot implicitly declare zero for parts absent from it.
    for part in sorted({r['part'] for r in current if r['kind']=='receipt'}-covered):
        for kind in ('opening','settlement'):
            if kind=='opening' and prior is not None:continue
            if sources and not any(r['part']==part and r['kind']==kind for r in current):
                issues.append({'code':'supplier_coverage','message':part+' '+('이월' if kind=='opening' else '정산')+' 자료가 촉매사 파일에 없습니다. 누락 자료를 확인해주세요.'})
    return {'rows':rows,'issues':issues,'pending':pending,'entries':entries,'source_ids':[s['id'] for s in sources],
            'connected':{kind:sum(r['kind']==kind for r in rows) for kind in ('opening','settlement')}}


def save(payload):
    from . import closing
    period=payload.get('period');p=closing.preview(period)
    if payload.get('fingerprint')!=p['fingerprint']:raise ValueError('자료가 변경되었습니다. 새로고침 후 확인해주세요')
    match=next((r for r in p['supplier_allocation']['entries'] if r['source_id']==payload.get('source_id') and r['part']==payload.get('part') and r['kind']==payload.get('kind')),None)
    if not match or not match['editable']:raise ValueError('이 항목은 배부 입력 대상이 아닙니다. 기존 자료를 확인해주세요')
    reason=str(payload.get('reason','')).strip()
    if not reason:raise ValueError('확인 사유를 입력해주세요')
    values=payload.get('values',{})
    if not isinstance(values,dict) or not values:raise ValueError('납품처별 수량을 입력해주세요')
    normalized={}
    for customer,value in values.items():
        if customer not in CUSTOMERS:raise ValueError('등록된 납품처를 선택해주세요')
        q=D(imports.number(value,True))
        if q<0 or q!=q.to_integral_value():raise ValueError('수량은 0 이상의 정수로 입력해주세요')
        normalized[customer]=str(q)
    if sum(map(D,normalized.values()),D(0))!=D(match['total']):raise ValueError('납품처별 합계가 원본 수량과 같아야 합니다')
    if match['part']=='28991-4C520' and any(c!='현대 전주' and D(q) for c,q in normalized.items()):raise ValueError('전주공장 직사급 품번입니다')
    store.backup()
    with store.db() as c:
        meta=json.loads(c.execute('SELECT meta FROM sources WHERE id=?',(match['source_id'],)).fetchone()[0])
        meta.setdefault('supplier_allocations',{}).setdefault(match['part'],{})[match['kind']]={'values':normalized,'reason':reason,'updated':store.stamp()}
        c.execute('UPDATE sources SET meta=? WHERE id=?',(store.encode(meta),match['source_id']))
        store.audit(c,'supplier_allocation',{**payload,'before':match.get('values'),'after':normalized})
    return {'saved':True}
