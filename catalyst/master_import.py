"""BOM / ERP adapters. Never run workbook macros or infer dates from filenames."""
import hashlib
import json
import re
from decimal import Decimal
from . import imports, store


def part(value):
    value=str(value or '').strip().upper()
    value=re.sub(r'^(R600|M|H)(?=\d)', '', value)
    return re.sub(r'_CKD$', '', value)


def identify(data):
    if {'BOM_마스터','촉매사_마스터'} <= data.keys(): return 'BOM 마스터'
    for rows in data.values():
        if any({'구매거래처','품번','통화','단가','적용종료일'} <= set(r) for r in rows[:10]):
            return '구매단가등록'
    return None


def read(sid,expected):
    with store.db() as c: source=c.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
    if not source or source['status'] in ('cancelled','deleted'): raise ValueError('사용할 등록 자료를 선택해주세요')
    data=imports.tables(imports.source_path(source))
    if identify(data)!=expected: raise ValueError(expected+' 양식이 아닙니다')
    return source,data


def preview(payload):
    effective=imports.day(payload.get('effective_date'))
    bom,data=read(int(payload['bom_id']),'BOM 마스터')
    erp,prices=read(int(payload['price_id']),'구매단가등록')
    for sheet,expected in {
        'BOM_마스터':{2:'촉매 마감처',5:'촉매 사용구분',12:'촉매 입력품번'},
        '촉매사_마스터':{0:'촉매 입력품번',1:'촉매사'},
    }.items():
        headers=data[sheet][7] if len(data[sheet])>7 else []
        if any(len(headers)<=i or headers[i]!=name for i,name in expected.items()):
            raise ValueError(sheet+'의 8행 열 제목이 변경되었습니다. 양식을 확인해주세요')
    suppliers={}; links={}; errors=[]
    for i,r in enumerate(data['촉매사_마스터'][8:],9):
        if not r[0]:continue
        p=part(r[0]); supplier=str(r[1] or '').strip()
        if not supplier: errors.append(f'촉매사_마스터 {i}행: {p} 촉매사 누락')
        if p in suppliers and suppliers[p]!=supplier: errors.append(f'{p} 촉매사 중복 충돌')
        suppliers[p]=supplier
    for i,r in enumerate(data['BOM_마스터'][8:],9):
        if not any(r):continue
        if r[5]=='미사용':continue
        if r[5]!='사용': errors.append(f'BOM {i}행: 사용구분 확인 필요');continue
        p=part(r[12]); customer=str(r[2] or '').strip()
        if not p or not customer: errors.append(f'BOM {i}행: 촉매 입력품번 또는 마감처 누락');continue
        if p=='28991-4C520':customer='현대 전주'
        if p not in suppliers:errors.append(f'BOM {i}행: {p} 촉매사 미등록')
        key=(p,customer)
        if key not in links:links[key]={'factory':customer,'supplier':suppliers.get(p,''),'bom_rows':[]}
        links[key]['bom_rows'].append(i)
    candidates={}
    for sheet,rs in prices.items():
        for hi,headers in enumerate(rs[:10]):
            if not {'구매거래처','품번','통화','단가','적용종료일'} <= set(headers):continue
            cols={h:i for i,h in enumerate(headers) if h}
            for i,r in enumerate(rs[hi+1:],hi+2):
                def get(k):return r[cols[k]] if k in cols and cols[k]<len(r) else None
                p=part(get('품번'))
                if p not in suppliers:continue
                if get('통화')!='KRW':errors.append(f'{sheet} {i}행: 원화 단가가 아닙니다');continue
                end=get('적용종료일')
                if end and imports.day(end)<effective:continue
                value=imports.number(get('단가'),True)
                if Decimal(value)<0:errors.append(f'{sheet} {i}행: 음수 단가');continue
                candidates.setdefault(p,[]).append({'price':value,'sheet':sheet,'row':i,'purchase_customer':get('구매거래처'),'input_date':get('입력일'),'retroactive_date':get('적용일(소급)'),'price_type':get('단가구분')})
            break
    if not suppliers or not links: errors.append('BOM 품번 또는 사용 중인 마감처 연결이 없습니다')
    rows=[]; changes=[]; missing=[]
    with store.db() as c:
        existing=[dict(r) for r in c.execute("SELECT r.* FROM records r JOIN batches b ON b.id=r.batch_id WHERE b.active=1 AND r.kind='price' AND r.customer='' AND r.date<=? ORDER BY r.date,r.id",(effective,))]
        revision=c.execute('SELECT COALESCE(MAX(id),0) FROM audit').fetchone()[0]
    old={r['part']:r['price'] for r in existing}
    for p,supplier in suppliers.items():
        rows.append({'kind':'part','part':p,'date':effective,'provenance':{'file':bom['name'],'source_id':bom['id'],'sheet':'촉매사_마스터','supplier':supplier}})
        matches=candidates.get(p,[])
        values={Decimal(r['price']) for r in matches}
        if not values:missing.append(p);continue
        if len(values)>1:errors.append(f'{p}: ERP 구매거래처별 단가가 서로 다릅니다');continue
        value=str(next(iter(values)))
        rows.append({'kind':'price','part':p,'price':value,'date':effective,'provenance':{'file':erp['name'],'source_id':erp['id'],'rows':matches,'reason':'사용자가 확인한 적용 기준일'}})
        if p not in old or Decimal(old[p])!=Decimal(value):changes.append({'part':p,'before':old.get(p),'after':value})
    for (p,customer),link in links.items():
        rows.append({'kind':'part','part':p,'customer':customer,'date':effective,'provenance':{'file':bom['name'],'source_id':bom['id'],'sheet':'BOM_마스터','link':link}})
    # Missing rates on an active BOM block import, dormant catalog items remain visible as warnings.
    used={p for p,_ in links}
    errors.extend(f'{p}: 사용 중인 BOM 품번의 구매단가 누락' for p in missing if p in used)
    result={'effective_date':effective,'bom_id':bom['id'],'price_id':erp['id'],'rows':rows,'changes':changes,'missing':missing,'errors':errors,'parts':len(suppliers),'links':len(links),'prices':sum(r['kind']=='price' for r in rows)}
    result['fingerprint']=hashlib.sha256((store.encode(result)+str(revision)).encode()).hexdigest()
    return result


def apply(payload):
    result=preview(payload)
    if result['errors']:raise ValueError('BOM·단가 확인 사항을 해결해주세요: '+' / '.join(result['errors'][:5]))
    if payload.get('fingerprint')!=result['fingerprint']:raise ValueError('자료가 변경되었습니다. 다시 미리보기해주세요')
    if not str(payload.get('reason','')).strip():raise ValueError('변경 사유가 필요합니다')
    backup=store.backup()
    scope='bom-erp-master:'+result['effective_date']
    with store.db() as c:
        for sid in (result['bom_id'],result['price_id']):
            if c.execute('SELECT 1 FROM batches WHERE source_id=? AND active=1',(sid,)).fetchone():
                raise ValueError('이미 반영 중인 마스터 파일입니다. 새 파일을 등록하거나 기존 반영을 취소해주세요.')
        c.execute('UPDATE batches SET active=0 WHERE scope=?',(scope,))
        bids={}
        for sid in (result['bom_id'],result['price_id']):
            bids[sid]=c.execute('INSERT INTO batches(source_id,scope,mode,created) VALUES(?,?,?,?)',(sid,scope,'replace',store.stamp())).lastrowid
            c.execute("UPDATE sources SET status='imported' WHERE id=?",(sid,))
        for raw in result['rows']:
            r=imports.normalize(raw);prov=raw['provenance'];prov['reason']=payload['reason']
            c.execute('INSERT INTO records(batch_id,kind,part,customer,date,quantity,price,amount,note,provenance) VALUES(?,?,?,?,?,?,?,?,?,?)',(bids[prov['source_id']],r['kind'],r['part'],r['customer'],r['date'],r['quantity'],r['price'],r['amount'],r['note'],store.encode(prov)))
        store.audit(c,'bom_erp_master',{'backup':backup,'reason':payload['reason'],'effective_date':result['effective_date'],'sources':[result['bom_id'],result['price_id']]})
    return {'backup':backup,'count':len(result['rows'])}
