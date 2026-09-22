"""Supplier statements are comparison evidence, never a second ERP receipt ledger."""
import hashlib
import json
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal
from . import imports, store

TYPES={'umicore':'한국유미코아 마감자료','heesung':'희성촉매 마감자료'}

def clean(value):
    return re.sub(r'\s+','',str(value or '')).lower()

def remark_allocation(note):
    """Only accept a complete quantity/customer expression, not incidental numbers."""
    aliases={'글로비스':'현대 글로비스','전주':'현대 전주','모비스':'현대 모비스','위아':'현대 위아',
             '아산':'현대 아산','울산':'현대 울산','광명':'기아 광명','화성':'기아 화성','광주':'기아 광주'}
    result=defaultdict(Decimal)
    for term in str(note or '').strip().split('+'):
        match=re.fullmatch(r'\s*(\d+(?:,\d{3})*)\s*개\s*([가-힣]+)\s*',term)
        if not match or match[2] not in aliases:return None
        result[aliases[match[2]]]+=Decimal(match[1].replace(',',''))
    return {k:str(v) for k,v in result.items()}

def layout(rows):
    for index, row in enumerate(rows[:8]):
        labels=[clean(v) for v in row]
        if {'품번','전월적송재고','total납품','당월마감수량','당월적송수량'}<=set(labels):
            return 'umicore',index,labels
        if {'품번','적송(이월)','출하','계','적송+출하','차이'}<=set(labels):
            return 'heesung',index,labels
    return None

def candidates(data):
    matches=[(name,rows,layout(rows)) for name,rows in data.items() if layout(rows)]
    if matches and all(m[2][0]=='heesung' for m in matches):
        named=[m for m in matches if re.fullmatch(r'\d{1,2}월\s*마감(?:자료)?',m[0])]
        if named:return named
    return matches

def identify(data):
    matches=candidates(data)
    return TYPES[matches[0][2][0]] if len(matches)==1 else None

def meta_type(meta):
    data={s['name']:[h['cells'] for h in s.get('headers',[]) if h['row']<=8] for s in meta.get('sheets',[])}
    return identify(data)

def parse(data,period):
    if not re.fullmatch(r'\d{4}-\d{2}',str(period or '')):raise ValueError('마감 월을 선택해주세요')
    month=date.fromisoformat(period+'-01').month
    matches=candidates(data)
    if len(matches)!=1:raise ValueError('촉매사 마감 표를 하나로 찾을 수 없습니다. 파일 양식 확인이 필요합니다.')
    sheet,table,(supplier,header,labels)=matches[0]
    # Sheet names may corroborate a month; filenames never determine accounting dates.
    if supplier=='heesung':
        hint=re.search(r'(\d{1,2})월',sheet)
        if hint and int(hint[1])!=month:raise ValueError(f'시트는 {hint[1]}월 자료입니다. 선택한 마감 월을 확인해주세요.')
    def col(label):
        if labels.count(label)!=1:raise ValueError('중복·누락 열 제목: '+label)
        return labels.index(label)
    pc=col('품번')
    columns={'opening':col('전월적송재고' if supplier=='umicore' else '적송(이월)'),
             'delivery':col('total납품' if supplier=='umicore' else '출하'),
             'settlement':col('당월마감수량' if supplier=='umicore' else '계'),
             'closing':col('당월적송수량' if supplier=='umicore' else '차이')}
    if supplier=='umicore':
        sub=[clean(v) for v in table[header+1]]
        total_columns=[i for i in range(columns['settlement'],columns['closing']) if i<len(sub) and sub[i]=='total']
        if len(total_columns)!=1:raise ValueError('당월 마감 Total 열을 찾을 수 없습니다')
        columns['settlement']=total_columns[0]
    def value(row,c):return row[c] if c<len(row) else None
    def number(row,c):return Decimal(imports.number(value(row,c)) or '0')
    items=[]; controls=[]; totals=defaultdict(Decimal); warnings=[]
    for index,row in enumerate(table[header+1:],header+2):
        if supplier=='umicore' and index==header+2:continue
        p=str(value(row,pc) or '').strip().upper()
        if not p:
            if any(clean(v)=='total' for v in row[:pc+1]):
                controls.append(row)
                break
            elif any(number(row,c) for c in columns.values()):
                # Umicore's second header is text, not a detail row.
                raise ValueError(f'{sheet} {index}행: 수량은 있지만 품번이 없습니다')
            continue
        if not re.fullmatch(r'(?:R600)?[A-Z0-9]{5}-[A-Z0-9]{5}',p):raise ValueError(f'{sheet} {index}행 품번 확인 필요: {p}')
        if p.startswith('R600'):p=p[4:]
        amounts={k:number(row,c) for k,c in columns.items()}
        if any(q<0 for q in amounts.values()):warnings.append(f'{sheet} {index}행 {p}: 음수 수량이 있어 반품·조정 사유 확인이 필요합니다. 원본값을 그대로 보관합니다.')
        if amounts['opening']+amounts['delivery']-amounts['settlement']!=amounts['closing']:
            raise ValueError(f'{sheet} {index}행 {p}: 이월 + 납품 − 정산이 잔량과 다릅니다')
        for key,q in amounts.items():totals[key]+=q
        allocation=None
        if supplier=='heesung':
            allocation=defaultdict(Decimal)
            aliases={'위아평택':'현대 위아','위아서산':'현대 위아','위아서산(디젤)':'현대 위아','위아서산(카파)':'현대 위아',
                     '아산':'현대 아산','기아화성':'기아 화성','기아광주':'기아 광주','기아광명':'기아 광명',
                     '울산':'현대 울산','울산ckd':'현대 울산','글로비스':'현대 글로비스','세종':'세종공업','모비스':'현대 모비스'}
            for c in range(columns['delivery']+1,columns['settlement']):
                customer=aliases.get(labels[c]);q=number(row,c)
                if not customer:raise ValueError(f'{sheet}: 납품처 열 확인 필요: {labels[c]}')
                if q:allocation[customer]+=q
            if sum(allocation.values(),Decimal(0))!=amounts['settlement']:raise ValueError(f'{sheet} {index}행 납품처 합계와 정산 계가 다릅니다')
            allocation={k:str(v) for k,v in allocation.items()}
        note=str(value(row,labels.index('비고')) or '') if '비고' in labels else ''
        items.append({'part':p,**{k:str(v) for k,v in amounts.items()},'sheet':sheet,'row':index,'settlement_allocation':allocation,
                      'remark':note,'remark_allocation':remark_allocation(note) if supplier=='umicore' else None,
                      'counterparty':'전주공장' if p=='28991-4C520' else TYPES[supplier].replace(' 마감자료','')})
    if not items:raise ValueError('마감 품목이 없습니다')
    if supplier=='heesung':controls=[table[header-1]] if header>0 else []
    if len(controls)!=1:raise ValueError('전체 합계 행을 하나로 확인할 수 없습니다')
    for key,c in columns.items():
        if totals[key]!=Decimal(imports.number(value(controls[0],c),True)):
            raise ValueError(f'{sheet}: {key} 상세 합계와 전체 합계가 다릅니다')
    return {'supplier':supplier,'type':TYPES[supplier],'period':period,'sheet':sheet,'items':items,
            'parts':len({r['part'] for r in items}),'totals':{k:str(v) for k,v in totals.items()},
            'warnings':warnings,'quantity_label':'Total 납품' if supplier=='umicore' else '출하'}

def registered(c):
    result=[]
    for row in c.execute("SELECT * FROM sources WHERE status NOT IN ('deleted','cancelled')"):
        info=json.loads(row['meta']).get('supplier_registration')
        if info and info.get('active'):result.append({**info,'source_id':row['id'],'name':row['name']})
    return result

def compare(result,c,sid):
    erp=defaultdict(Decimal)
    records=c.execute("SELECT r.part,r.quantity FROM records r JOIN batches b ON b.id=r.batch_id WHERE b.active=1 AND r.kind='receipt' AND substr(r.date,1,7)=?",(result['period'],)).fetchall()
    for r in records:erp[r['part']]+=Decimal(r['quantity'])
    supplied=defaultdict(Decimal)
    for r in result['items']:supplied[r['part']]+=Decimal(r['delivery'])
    other_parts={r['part'] for s in registered(c) if s['source_id']!=sid and s['period']==result['period'] and s['supplier']!=result['supplier'] for r in s['items']}
    details=[{'part':p,'supplier_quantity':str(q),'erp_quantity':str(erp[p]) if records else None,
              'difference':str(erp[p]-q) if records and p not in other_parts else None,
              'overlap':p in other_parts} for p,q in sorted(supplied.items())]
    return {'erp_available':bool(records),'differences':[r for r in details if r['overlap'] or r['difference'] not in ('0',None)],
            'matched':sum(r['difference']=='0' for r in details),'details':details}

def preview(sid,period):
    with store.db() as c:
        source=c.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
        if not source or source['status'] in ('deleted','cancelled'):raise ValueError('사용할 마감자료를 선택해주세요')
        path=imports.source_path(source)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=source['hash']:raise ValueError('보관 원본이 없거나 변경되었습니다')
        result=parse(imports.tables(path),period)
        existing=json.loads(source['meta']).get('supplier_registration',{})
        result['errors']=[]
        if existing and existing['period']!=period:result['errors'].append('이미 다른 월로 등록한 파일입니다. 월을 정정하려면 자료를 삭제한 후 다시 등록해주세요.')
        if c.execute('SELECT 1 FROM batches WHERE source_id=? AND active=1',(sid,)).fetchone():
            result['errors'].append('이 파일은 일반 열 연결로 계산에 반영되어 있습니다. 중복 방지를 위해 삭제 후 다시 등록해주세요.')
        result['registered']=bool(existing.get('active') and existing['period']==period)
        result['replaces']=[{'id':s['source_id'],'name':s['name']} for s in registered(c) if s['source_id']!=sid and s['supplier']==result['supplier'] and s['period']==period]
        result['comparison']=compare(result,c,sid)
        revision=c.execute('SELECT COALESCE(MAX(id),0) FROM audit').fetchone()[0]
    result['fingerprint']=hashlib.sha256((store.encode(result)+str(revision)).encode()).hexdigest()
    return result

def apply(sid,payload):
    result=preview(sid,payload.get('period'))
    if result['errors']:raise ValueError(' / '.join(result['errors']))
    if result['fingerprint']!=payload.get('fingerprint'):raise ValueError('자료가 변경되었습니다. 다시 미리보기해주세요')
    if result['registered']:return {'duplicate':True,'period':result['period']}
    store.backup()
    with store.db() as c:
        for old in result['replaces']:
            meta=json.loads(c.execute('SELECT meta FROM sources WHERE id=?',(old['id'],)).fetchone()[0])
            meta['supplier_registration']['active']=False
            c.execute('UPDATE sources SET meta=? WHERE id=?',(store.encode(meta),old['id']))
        meta=json.loads(c.execute('SELECT meta FROM sources WHERE id=?',(sid,)).fetchone()[0])
        meta['type']=result['type']
        meta['supplier_registration']={k:result[k] for k in ('period','supplier','items','totals','sheet','quantity_label','parts')}
        meta['supplier_registration']['active']=True
        c.execute("UPDATE sources SET status='reference',meta=? WHERE id=?",(store.encode(meta),sid))
        c.execute('UPDATE issues SET resolved=1 WHERE source_id=?',(sid,))
        store.audit(c,'supplier_registration',{'source_id':sid,'period':result['period'],'replaces':result['replaces'],'totals':result['totals']})
    return {'period':result['period'],'duplicate':False}
