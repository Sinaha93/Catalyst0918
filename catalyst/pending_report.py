"""Shared pending-detail/subtotal rows for Excel and PowerPoint."""
from decimal import Decimal as D

FIELDS=('opening','receipt','settlement','closing','closing_amount')

def grouped_rows(details,customers):
    result=[]
    for customer in customers:
        rows=[r for r in details if r['customer']==customer and
              (D(r['opening'])!=0 or D(r['closing'])!=0 or r.get('note'))]
        if not rows:continue
        for r in rows:
            result.append({**r,'subtotal':False,'number':len([x for x in result if not x['subtotal']])+1})
        result.append({'customer':customer,'subtotal':True,
            **{key:str(sum(D(r[key]) for r in rows)) for key in FIELDS}})
    return result

def paginate(rows,capacity=18):
    """Keep small customer groups together and never orphan a subtotal."""
    if capacity<2:raise ValueError('Page capacity must be at least two')
    pages=[];page=[];group=[]
    for row in rows:
        group.append(row)
        if not row['subtotal']:continue
        if len(group)<=capacity:
            if len(page)+len(group)>capacity:pages.append(page);page=[]
            page.extend(group)
        else:
            if page:pages.append(page);page=[]
            while len(group)>capacity:
                take=capacity if len(group)-capacity!=1 else capacity-1
                pages.append(group[:take]);group=group[take:]
            page=group[:]
        group=[]
    if group:raise ValueError('Customer group is missing its subtotal')
    if page:pages.append(page)
    return pages or [[]]

def cells(row,ppt=False):
    if row['subtotal']:
        values=['',row['customer']+' 소계','','','','']
    else:
        q=D(row['closing']);amount=D(row['closing_amount'])
        values=[row['number'],row['customer'],row.get('vehicle',''),row['part'],row.get('price_type',''),
                amount/q if q else None]
    values += [D(row[k]) for k in FIELDS]
    values.append('' if row['subtotal'] else row.get('note',''))
    if ppt:
        return [f'{v/1000:,.3f}' if i==10 else f'{v:,.2f}' if i==5 and isinstance(v,D)
                else f'{v:,.0f}' if isinstance(v,D) else str(v) if v is not None else ''
                for i,v in enumerate(values)]
    return [float(v) if isinstance(v,D) else v for v in values]

def write_excel(ws,rows):
    end=max(1000,len(rows)+3)
    body=ws.Range(f'B4:M{end}')
    body.UnMerge();body.ClearContents()
    body.Interior.Pattern=-4142
    body.Font.Color=0;body.Font.Bold=False
    body.FormatConditions.Delete()
    body.Borders.LineStyle=-4142
    if not rows:return
    area=ws.Range(f'B4:M{len(rows)+3}')
    area.Font.Name='맑은 고딕';area.Font.Size=10
    area.RowHeight=20
    area.Borders.LineStyle=1;area.Borders.Weight=2
    area.VerticalAlignment=-4108
    area.HorizontalAlignment=-4108
    ws.Range(f'G4:G{len(rows)+3}').NumberFormat='#,##0.00'
    ws.Range(f'H4:K{len(rows)+3}').NumberFormat='#,##0'
    ws.Range(f'L4:L{len(rows)+3}').NumberFormat='#,##0.000,'
    ws.Range(f'G4:L{len(rows)+3}').HorizontalAlignment=-4152
    ws.Range(f'M4:M{len(rows)+3}').WrapText=True
    first=4
    for index,row in enumerate(rows,4):
        ws.Range(f'B{index}:M{index}').Value=(tuple(cells(row)),)
        if row['subtotal']:
            band=ws.Range(f'B{index}:M{index}')
            band.Interior.Color=0xD9EAFB
            band.Font.Bold=True
            ws.Range(f'B{index}:G{index}').Merge()
            ws.Cells(index,2).Value=row['customer']+' 소계'
            for col in 'HIJKL':
                ws.Range(f'{col}{index}').Formula=f'=SUM({col}{first}:{col}{index-1})'
            first=index+1
    area.Rows.AutoFit()
