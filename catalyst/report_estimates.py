"""Separate planning estimates from the recorded closing valuation in exports."""
from decimal import Decimal
import re

def report_note(row):
    note=row.get('note','')
    if any(e.get('migration')=='2026-08 reviewed historical bootstrap' for e in row.get('evidence',[])):
        note=note.replace('기존 8월 마감 정산수량 이관','').replace('기존 마감 이월 수량; 등록 단가 기준 평가','')
        note=note.strip(' /')
    return note


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


def append_ppt(path,snapshot):
    rows=estimate_rows(snapshot)
    if not rows:return
    import win32com.client
    app=win32com.client.DispatchEx('PowerPoint.Application')
    deck=None
    try:
        deck=app.Presentations.Open(str(path),ReadOnly=False,Untitled=False,WithWindow=False)
        for r in rows:
            slide=deck.Slides(4).Duplicate().Item(1)
            slide.MoveTo(deck.Slides.Count)
            for i in range(slide.Shapes.Count,0,-1):
                shape=slide.Shapes(i)
                if shape.HasTable:shape.Delete();continue
                if shape.HasTextFrame and shape.TextFrame.HasText:
                    text=shape.TextFrame.TextRange.Text
                    if '미정산 품목' in text:shape.TextFrame.TextRange.Text='▣ 예상 정산금액 (참고)'
                    elif '단위:' in text:shape.TextFrame.TextRange.Text='단위: 개 / 원'
            def textbox(text,x,y,w,h,size):
                shape=slide.Shapes.AddTextbox(1,x,y,w,h)
                shape.TextFrame.TextRange.Text=text
                shape.TextFrame.TextRange.Font.Name='맑은 고딕'
                shape.TextFrame.TextRange.Font.Size=size
                shape.TextFrame.WordWrap=True
                return shape
            textbox(r['customer']+' / '+r['part'],24,85,732,40,22)
            values=[['항목','기록 기준','추정 기준'],
                ['미결 수량',f"{r['quantity']:,.0f}",f"{r['quantity']:,.0f}"],
                ['평가 단가(원)',f"{r['recorded_rate']:,.2f}" if r['recorded_rate'] is not None else '해당 없음',f"{r['estimated_price']:,.2f}"],
                ['금액(원)',f"{r['recorded_amount']:,.0f}",f"{r['estimated_amount']:,.0f}"]]
            table=slide.Shapes.AddTable(4,3,24,145,732,160).Table
            for ri,values_row in enumerate(values,1):
                for ci,value in enumerate(values_row,1):
                    shape=table.Cell(ri,ci).Shape
                    shape.TextFrame.TextRange.Text=value
                    shape.TextFrame.TextRange.Font.Name='맑은 고딕'
                    shape.TextFrame.TextRange.Font.Size=20
                    shape.TextFrame.TextRange.Font.Color.RGB=0
                    shape.Fill.ForeColor.RGB=0xB5D6FF if ri==1 else 0xFFFFFF
            textbox('추정 금액은 실제 정산 및 다음 달 이월 금액에 반영하지 않습니다.',24,330,732,55,18)
            textbox('추정 사유: '+r['reason'],24,395,732,95,16)
        for index,slide in enumerate(deck.Slides,1):
            for shape in slide.Shapes:
                if shape.HasTextFrame and shape.TextFrame.HasText:
                    if re.fullmatch(r'\d+/\d+',shape.TextFrame.TextRange.Text.strip()):
                        shape.TextFrame.TextRange.Text=f'{index}/{deck.Slides.Count}'
        deck.Save()
    finally:
        if deck is not None:deck.Close()
        app.Quit()
