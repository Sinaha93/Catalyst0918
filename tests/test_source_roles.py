from catalyst.source_roles import describe


def test_roles_do_not_depend_on_filename():
    assert describe({'type':'BOM 마스터'},[])['roles']==['bom']
    assert describe({'type':'구매단가등록'},[])['roles']==['price']
    assert describe({'sheets':[{'name':'납품 Summary'}]},[])['roles']==['umicore']
    assert describe({'sheets':[{'name':'8월 마감자료'}]},[])['roles']==['heesung']


def test_periods_and_legacy_master():
    result=describe({},[{'kind':'receipt','date':'2026-08-31'},{'kind':'receipt','date':'2026-09-01'}])
    assert result['applied_months']=={'receipt':['2026-08','2026-09']}
    assert result['requirement_label']=='필수 자료'
    assert describe({},[{'kind':'price','date':'2026-08-01'}])['requirement_label']=='기존 마스터 · 대체 예정'
    assert describe({'type':'보고서 기준자료'},[])['requirement_label']=='필수 아님 · PPT'
    assert describe({},[])['requirement_label']=='역할 확인 필요'
