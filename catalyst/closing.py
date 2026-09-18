from collections import defaultdict
from decimal import Decimal
from datetime import date
import calendar
import hashlib
import json
from . import store

D=Decimal

def preview(period):
    start=date.fromisoformat(period+'-01')
    end=date(start.year,start.month,calendar.monthrange(start.year,start.month)[1]).isoformat()
    with store.db() as c:
        records=[dict(r) for r in c.execute('SELECT r.*, b.source_id,b.scope FROM records r JOIN batches b ON r.batch_id=b.id WHERE b.active=1 AND r.date<=? ORDER BY r.date,r.id',(end,))]
        previous=f'{start.year-1}-12' if start.month==1 else f'{start.year}-{start.month-1:02d}'
        prior=c.execute('SELECT snapshot FROM runs WHERE period=? ORDER BY version DESC LIMIT 1',(previous,)).fetchone()
        links=[dict(r) for r in c.execute('SELECT * FROM part_links')]
        estimates=[dict(r) for r in c.execute('SELECT * FROM price_estimates WHERE period=? AND enabled=1 ORDER BY customer,part',(period,))]
    parts={r['part'] for r in records if r['kind']=='part'}|{r['part'] for r in links}
    prices=[r for r in records if r['kind']=='price']
    current=[r for r in records if r['date'].startswith(period) and r['kind'] not in ('part','price')]
    issues=[]
    details={}
    def item(part,customer):
        return details.setdefault((part,customer),{'part':part,'customer':customer,'opening':D(0),'receipt':D(0),'settlement':D(0),'shipment':D(0),'adjustment':D(0),'plan':D(0),'receipt_amount':D(0),'settlement_amount':D(0),'opening_amount':D(0),'closing_amount':D(0),'note':'','evidence':[]})
    # Explicit opening records replace prior closing only for their own key.
    explicit={(r['part'],r['customer']) for r in current if r['kind']=='opening'}
    if prior:
        for row in json.loads(prior[0])['details']:
            if (row['part'],row['customer']) not in explicit:
                target=item(row['part'],row['customer'])
                target['opening']=D(row['closing'])
                target['opening_amount']=D(row['closing_amount']) if row['closing_amount'] is not None else None
                target['evidence'].append({'prior_period':previous})
    if not current:
        issues.append({'code':'empty','message':'선택한 월의 거래 자료가 없습니다'})
    kinds={r['kind'] for r in current}
    for kind,label in [('receipt','입고'),('settlement','계산서·정산')]:
        if kind not in kinds:
            issues.append({'code':'missing_source','message':label+' 자료가 필요합니다'})
    if not prior and 'opening' not in kinds:
        issues.append({'code':'missing_opening','message':'전월 확정 마감 또는 기초 이월 자료가 필요합니다. 이월이 없으면 0으로 명시해주세요.'})
    for r in current:
        target=item(r['part'],r['customer'])
        q=D(r['quantity'])
        target[r['kind']]+=q
        target['note']=r['note'] or target['note']
        prov=json.loads(r['provenance'])
        target['evidence'].append({'record_id':r['id'],**prov})
        if r['part'] not in parts:
            issues.append({'code':'part','message':r['part']+' 품번 마스터 누락','evidence':prov})
        if q<0 and not r['note']:
            issues.append({'code':'negative','message':r['part']+' 음수 수량의 반품·조정 사유 필요','evidence':prov})
        applicable=[p for p in prices if p['part']==r['part'] and p['customer'] in ('',r['customer']) and p['date']<=r['date']]
        applicable.sort(key=lambda p:(bool(p['customer']),p['date'],p['id']))
        price=D(r['price']) if r['price'] is not None else D(applicable[-1]['price']) if applicable else None
        amount=D(r['amount']) if r['amount'] is not None else q*price if price is not None else None
        field={'receipt':'receipt_amount','settlement':'settlement_amount','opening':'opening_amount'}.get(r['kind'])
        if field:
            if amount is None and q!=0:
                target[field]=None
                issues.append({'code':'price','message':r['part']+' '+r['date']+' 적용 단가 또는 금액 누락','evidence':prov})
            elif target[field] is not None:
                target[field]+=amount or D(0)
    for row in details.values():
        link=next((r for r in links if r['part']==row['part'] and r['customer']==row['customer']),{})
        row.update({k:link.get(k,'') for k in ('factory','supplier','vehicle','price_type')})
        row['closing']=row['opening']+row['receipt']+row['adjustment']-row['settlement']
        row['closing_amount']=None if any(row[k] is None for k in ('opening_amount','receipt_amount','settlement_amount')) else row['opening_amount']+row['receipt_amount']-row['settlement_amount']
        if row['adjustment']:
            # Quantity-only adjustments cannot silently change valuation.
            row['closing_amount']=None
            issues.append({'code':'adjustment','message':row['part']+' 수량 조정의 금액 처리가 필요합니다. 금액을 포함한 입고/정산 정정으로 반영해주세요.'})
        if row['closing']<0:
            issues.append({'code':'balance','message':row['customer']+' '+row['part']+' 미결 수량이 음수입니다','evidence':row['evidence']})
        row['allocation_difference']=row['shipment']-row['receipt'] if 'shipment' in kinds else None
        estimate=next((e for e in estimates if e['part']==row['part'] and e['customer']==row['customer']),None)
        # Estimates are separate from recorded valuation and never carried forward.
        row['estimated_price']=D(estimate['price']) if estimate else None
        row['estimated_closing_amount']=row['closing']*D(estimate['price']) if estimate else None
        row['estimate_reason']=estimate['reason'] if estimate else ''
    groups=defaultdict(lambda:{k:D(0) for k in ('opening','receipt','settlement','closing','plan','settlement_amount','closing_amount')})
    for row in details.values():
        group=groups[row['customer']]
        for key in group:
            group[key]=None if group[key] is None or row[key] is None else group[key]+row[key]
    planned_customers={r['customer'] for r in current if r['kind']=='plan'}
    for customer,group in groups.items():
        if customer not in planned_customers:group['plan']=None
    result={'period':period,'details':list(details.values()),'customers':[{'customer':k,**v} for k,v in groups.items()],'issues':issues,'ready':not issues,'record_count':len(current),'source_ids':sorted({r['source_id'] for r in records if r['source_id']}),'input_snapshot':records,'estimate_snapshot':estimates}
    result=json.loads(store.encode(result))
    result['fingerprint']=hashlib.sha256(store.encode(result).encode()).hexdigest()
    return result

def finalize(period,fingerprint):
    result=preview(period)
    if not result['ready']:
        raise ValueError('미해결 항목을 처리한 후 마감을 확정해주세요')
    if result['fingerprint']!=fingerprint:
        raise ValueError('자료가 변경됐습니다. 미리보기를 새로 확인해주세요')
    from .reports import freeze_context
    result['report_context']=freeze_context(period)
    with store.db() as c:
        last=c.execute('SELECT version,snapshot FROM runs WHERE period=? ORDER BY version DESC LIMIT 1',(period,)).fetchone()
        if last and json.loads(last['snapshot'])['fingerprint']==fingerprint:
            raise ValueError('동일한 자료로 이미 확정한 마감입니다')
        version=last['version']+1 if last else 1
        rid=c.execute('INSERT INTO runs(period,version,snapshot,created) VALUES(?,?,?,?)',(period,version,store.encode(result),store.stamp())).lastrowid
        store.audit(c,'finalize',{'run_id':rid,'period':period,'version':version})
    store.backup()
    return {'id':rid,'version':version}
