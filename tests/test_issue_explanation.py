import json
from catalyst.issue_explanation import explain


def record():
    return {'part':'P','customer':'현대 모비스','kind':'settlement','date':'2026-05-31','quantity':'2','source_id':1,
            'provenance':json.dumps({'file':'촉매사.xlsx','rows':[{'sheet':'5월 마감','row':82}]})}


def test_source_location_and_imported_scope():
    sources=[{'id':2,'name':'BOM.xlsx','active':1,'meta':json.dumps({'type':'BOM 마스터'})},
             {'id':3,'name':'삭제된 기준.xlsx','active':0,'meta':json.dumps({'type':'BOM 마스터'})}]
    e=explain('part',record(),[],sources)
    assert e['found'][0]['row']==82 and e['found'][0]['sheet']=='5월 마감'
    assert [r['file'] for r in e['checked']]==['BOM.xlsx']
    assert '반영된' in e['missing'] and '파일 전체' in e['scope_note']


def test_future_price_and_customer_mismatch_not_claimed_absent():
    masters=[{'part':'P','kind':'price','customer':'현대 전주','date':'2026-06-01','source_id':2}]
    e=explain('price',record(),masters,[])
    assert '2026-06-01' in e['missing'] and '현대 전주' in e['missing']
    assert '찾지 못' not in e['missing']


def test_manual_and_missing_registered_master():
    r=record();r.update(source_id=None,provenance='{}')
    e=explain('price',r,[],[])
    assert e['found'][0]['file']=='직접 입력'
    assert '활성 반영 파일 없음' in e['checked'][0]['state']
