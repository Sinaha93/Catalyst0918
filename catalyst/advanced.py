"""Audited, month-scoped supplier exceptions and readable change history."""
import json
import re
from datetime import date
from . import store
from .august_bootstrap import CUSTOMERS


def rules():
    with store.db() as c:return [dict(r) for r in c.execute('SELECT * FROM part_rules ORDER BY period DESC,part')]


def save_rule(payload):
    period=str(payload.get('period',''));part=str(payload.get('part','')).strip().upper()
    customer=payload.get('customer');reason=str(payload.get('reason','')).strip()
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',period):raise ValueError('적용 월을 선택해주세요')
    if not re.fullmatch(r'[A-Z0-9]{5}-[A-Z0-9]{5}',part):raise ValueError('품번 형식을 확인해주세요')
    if customer not in CUSTOMERS or not reason:raise ValueError('납품처와 변경 사유를 입력해주세요')
    if part=='28991-4C520' and customer!='현대 전주':raise ValueError('확인된 전주공장 직사급 품번은 현대 전주로 유지해주세요')
    if not isinstance(payload.get('enabled'),bool):raise ValueError('사용 여부를 선택해주세요')
    with store.db() as c:
        old=c.execute('SELECT * FROM part_rules WHERE period=? AND part=?',(period,part)).fetchone()
        before=dict(old) if old else None
        if payload.get('before')!=before:raise ValueError('규칙이 변경되었습니다. 새로고침 후 수정해주세요')
        after={'period':period,'part':part,'customer':customer,'reason':reason,'enabled':int(payload['enabled']),'updated':store.stamp()}
        c.execute('INSERT INTO part_rules VALUES(?,?,?,?,?,?) ON CONFLICT(period,part) DO UPDATE SET customer=excluded.customer,reason=excluded.reason,enabled=excluded.enabled,updated=excluded.updated',tuple(after.values()))
        store.audit(c,'part_rule',{'before':before,'after':after,'reason':reason})
    return {'saved':True}


def history(before=0,action='',query='',since='',until='',limit=20):
    if before<0 or not 1<=limit<=100:raise ValueError('조회 범위를 확인해주세요')
    for value in (since,until):
        if value:date.fromisoformat(value)
    if since and until and since>until:raise ValueError('조회 시작일이 종료일보다 늦습니다')
    rows=[];query=query.strip().casefold()
    with store.db() as c:
        names={r['id']:r['name'] for r in c.execute('SELECT id,name FROM sources')}
        actions=[r[0] for r in c.execute('SELECT DISTINCT action FROM audit ORDER BY action')]
        for raw in c.execute("SELECT * FROM audit WHERE (?=0 OR id<?) AND (?='' OR action=?) AND (?='' OR substr(created,1,10)>=?) AND (?='' OR substr(created,1,10)<=?) ORDER BY id DESC",(before,before,action,action,since,since,until,until)):
            row=dict(raw);detail=json.loads(row['detail']);row['detail']=detail
            ids=detail.get('sources',[]) if isinstance(detail.get('sources'),list) else []
            ids=[i.get('id') if isinstance(i,dict) else i for i in ids]
            if detail.get('source_id'):ids.append(detail['source_id'])
            row['files']=[names[i] for i in ids if isinstance(i,int) and i in names]
            if query and query not in (store.encode(detail)+' '+ ' '.join(row['files'])).casefold():continue
            rows.append(row)
            if len(rows)>limit:break
    return {'items':rows[:limit],'next':rows[limit-1]['id'] if len(rows)>limit else None,'actions':actions}
