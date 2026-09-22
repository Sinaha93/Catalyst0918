from decimal import Decimal
from catalyst.pending_report import grouped_rows,paginate,cells

def detail(customer='C',**kw):
    return dict(customer=customer,part='P',opening='2',receipt='3',settlement='1',closing='4',closing_amount='4',note='',**kw)

def test_subtotals_and_actual_price():
    rows=grouped_rows([detail(),detail()],['C'])
    assert len(rows)==3 and rows[-1]['subtotal']
    assert rows[-1]['closing']=='8' and rows[-1]['closing_amount']=='8'
    assert cells(rows[0])[5]==1
    assert cells(rows[-1],ppt=True)[10]=='0.008'

def test_settled_opening_is_kept():
    r=detail();r.update(opening='2',receipt='0',settlement='2',closing='0',closing_amount='0')
    assert len(grouped_rows([r],['C']))==2
    r.update(opening='0',settlement='0')
    assert grouped_rows([r],['C'])==[]


def test_notes_and_fully_settled_current_receipts_do_not_force_inclusion():
    hidden=detail();hidden.update(opening='0',receipt='100',settlement='100',closing='0',closing_amount='0',note='월계획 / ERP 추출단가 / 구매단가등록_20260921.xlsx')
    visible=detail();visible.update(opening='0',receipt='10',settlement='6',closing='4',closing_amount='40')
    rows=grouped_rows([hidden,visible],['C'])
    assert len(rows)==2 and rows[0]['number']==1
    assert rows[-1]['receipt']=='10' and rows[-1]['settlement']=='6'
    assert rows[-1]['closing']=='4' and rows[-1]['closing_amount']=='40'
    hidden.update(receipt='0',settlement='0',note='개발 이벤트')
    assert grouped_rows([hidden],['C'])==[]

def test_pagination_no_orphan_and_no_loss():
    for count in range(1,75):
        rows=grouped_rows([detail() for _ in range(count)]+[detail('D')],['C','D'])
        pages=paginate(rows)
        assert all(len(p)<=18 and not p[0]['subtotal'] for p in pages)
        assert [r for p in pages for r in p]==rows
        assert sum(Decimal(r['closing_amount']) for p in pages for r in p if r['subtotal'])==4*(count+1)
