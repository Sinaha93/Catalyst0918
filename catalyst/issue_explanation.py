"""Human-readable diagnostics based on active imported data, not guessed workbook contents."""
import json

LABELS={'receipt':'ERP 입고','opening':'전월 이월','settlement':'당월 정산','plan':'월계획','shipment':'출하','adjustment':'수량 조정'}


def explain(code, record, masters, sources):
    part=record['part']; kind='part' if code=='part' else 'price'
    prov=json.loads(record['provenance'])
    source=next((s for s in sources if s['id']==record.get('source_id')), {})
    locations=prov.get('rows') or [prov]
    found=[]
    for location in locations:
        found.append({'source_id':prov.get('source_id') or record.get('source_id'),
                      'file':prov.get('file') or source.get('name') or '직접 입력',
                      'sheet':location.get('sheet',prov.get('sheet','')),'row':location.get('row'),
                      'kind':record['kind'],'quantity':record['quantity'],
                      'customer':record['customer'],'date':record['date']})
    expected_type='BOM 마스터' if kind=='part' else '구매단가등록'
    source_ids={m.get('source_id') for m in masters if m['kind']==kind}
    checked=[{'source_id':s['id'],'file':s['name'],'state':'반영된 기준 자료'} for s in sources if s.get('active') and (s['id'] in source_ids or json.loads(s['meta']).get('type')==expected_type)]
    related=[m for m in masters if m['kind']==kind and m['part']==part]
    if not checked:
        checked=[{'file':expected_type,'state':'활성 반영 파일 없음 · 직접 입력 기준도 함께 조회'}]
    if related:
        dates=sorted({m['date'] for m in related if m['date']>record['date']})
        customers=sorted({m['customer'] for m in related if m['customer'] not in ('',record['customer'])})
        reasons=[]
        if dates:reasons.append('등록된 적용일('+', '.join(dates)+')이 거래일 '+record['date']+'보다 늦습니다')
        if customers:reasons.append('다른 납품처('+', '.join(customers)+')용 기준만 있습니다')
        missing=' / '.join(reasons) or '이 거래에 적용 가능한 기준 값이 없습니다'
    else:
        missing='반영된 '+expected_type+' 데이터에서 '+part+(' 품번을 찾지 못했습니다.' if kind=='part' else '의 적용 단가를 찾지 못했습니다.')
    action=('BOM의 촉매사_마스터 품번과 BOM_마스터의 사용 여부·마감처를 확인한 뒤 BOM·구매단가 연결에서 다시 반영해주세요.'
            if kind=='part' else '구매단가등록의 품번·단가와 프로그램의 적용 기준일을 확인하고 다시 반영해주세요. BOM에서 제외된 품번이면 BOM부터 보완해주세요. 단가를 임의로 0원 처리하지 않습니다.')
    return {'found':found,'checked':checked,'missing':missing,'action':action,
            'summary':LABELS.get(record['kind'],record['kind'])+'에 수량 '+str(record['quantity'])+'개가 있으나 '+missing,
            'scope_note':'원본 파일 전체의 존재 여부가 아니라, 프로그램에 현재 반영된 데이터 기준입니다. 파일에 값이 있어도 제외·미반영된 경우 여기에는 없을 수 있습니다.'}
