"""Separate planning estimates from the recorded closing valuation in exports."""
from decimal import Decimal
import re

def report_note(row):
    note=row.get('note') or ''
    if any(e.get('migration')=='2026-08 reviewed historical bootstrap' for e in row.get('evidence',[])):
        note=note.replace('기존 8월 마감 정산수량 이관','').replace('기존 마감 이월 수량; 등록 단가 기준 평가','')
        note=note.strip(' /')
    # Export business reasons, not import provenance. Evidence stays in the snapshot.
    parts=re.split(r'\s+/\s+|\r?\n',note or '')
    return ' / '.join(p.strip() for p in parts if p.strip() and
        p.strip() not in {'월계획','ERP 추출단가','ERP 추출 단가'} and
        not re.fullmatch(r'.*\.(?:xlsx|xlsm|xls|csv|pptx)',p.strip(),re.IGNORECASE))


def estimate_rows(snapshot):
    result=[]
    for row in snapshot['details']:
        if row.get('estimated_price') is None:
            continue
        q=Decimal(row['closing']); price=Decimal(row['estimated_price'])
        amount=q*price
        if not price.is_finite() or price<0 or amount!=Decimal(row['estimated_closing_amount']):
            raise ValueError('예상 정산금액 스냅샷 불일치: '+row['part'])
        if row['closing_amount'] is None:raise ValueError('기록 기준 미결 금액을 확인해주세요')
        recorded=Decimal(row['closing_amount'])
        result.append({'part':row['part'],'customer':row['customer'],'quantity':q,
            'recorded_rate':recorded/q if q else None,'recorded_amount':recorded,
            'estimated_price':price,'estimated_amount':amount,'reason':row.get('estimate_reason','')})
    return result


def write_excel(ws,snapshot):
    rows=estimate_rows(snapshot)
    # Reserved area to the right, preserving all 14 existing worksheets.
    ws.Range('O1:V1000').ClearContents()
    if not rows:return
    ws.Range('O1').Value='예상 정산금액 (참고)'
    ws.Range('O2').Value='추정 금액은 실제 정산 및 다음 달 이월 금액에 반영하지 않습니다.'
    ws.Range('O4:V4').Value=(('품번','거래처','미결 수량','기록 기준 평가단가(원)','기록 기준 금액(원)','예상 단가(원)','예상 정산금액(원)','추정 사유'),)
    for index,r in enumerate(rows,5):
        ws.Range(f'O{index}:V{index}').Value=((r['part'],r['customer'],float(r['quantity']),float(r['recorded_rate']) if r['recorded_rate'] is not None else None,float(r['recorded_amount']),float(r['estimated_price']),float(r['estimated_amount']),r['reason']),)
    area=ws.Range(f'O4:V{len(rows)+4}')
    area.Font.Name='맑은 고딕';area.Font.Size=11
    ws.Range('O4:V4').Font.Bold=True
    ws.Range('O4:V4').Interior.Color=0xB5D6FF
    ws.Range('O:V').ColumnWidth=24
    ws.Range('V:V').ColumnWidth=55
    ws.Range(f'V5:V{len(rows)+4}').WrapText=True
    ws.Range(f'Q5:U{len(rows)+4}').NumberFormat='#,##0.00'
    area.Rows.AutoFit()
