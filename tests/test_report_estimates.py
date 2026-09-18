import pytest
from catalyst.report_estimates import estimate_rows, report_note

def detail(**overrides):
    return {'part':'P','customer':'C','closing':'7487','closing_amount':'7487',
            'estimated_price':'131518','estimated_closing_amount':'984675266','estimate_reason':'추정',**overrides}

def test_independent_report_amounts():
    original=detail()
    r=estimate_rows({'details':[original]})[0]
    assert r['recorded_amount']==7487 and r['estimated_amount']==984675266
    assert original['closing_amount']=='7487'
    assert estimate_rows({'details':[detail(estimated_price=None)]})==[]

def test_zero_and_invalid_snapshot():
    assert estimate_rows({'details':[detail(closing='0',closing_amount='0',estimated_closing_amount='0')]})[0]['recorded_rate'] is None
    with pytest.raises(ValueError):estimate_rows({'details':[detail(estimated_closing_amount='5')]})

def test_migration_text_not_business_reason():
    row={'note':'개발 이벤트 / 기존 마감 이월 수량; 등록 단가 기준 평가','evidence':[{'migration':'2026-08 reviewed historical bootstrap'}]}
    assert report_note(row)=='개발 이벤트'
    assert report_note({**row,'note':'기존 마감 이월 수량; 등록 단가 기준 평가'})==''
    assert '이관' in report_note({'note':'기존 8월 마감 정산수량 이관','evidence':[]})

def test_equivalent_decimal_format():
    assert estimate_rows({'details':[detail(estimated_closing_amount='984675266.00')]})[0]['estimated_amount']==984675266
