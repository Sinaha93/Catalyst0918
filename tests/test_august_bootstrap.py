from pathlib import Path
from decimal import Decimal
import copy
import pytest
from catalyst import store, closing, estimates, august_bootstrap as boot

ROOT=Path(__file__).resolve().parents[1]
NAMES={'master':'★촉매 관리 현황.xlsx','erp':'기간별구매거래처입고현황(8월).xlsx',
       'closing':'26년 8월 촉매 마감.xlsx','umicore':'우신공업 8월 한국유미코아촉매_0826_2차마감.xlsx',
       'heesung':'26년 8월 우신공업 출하실적.xlsx'}

@pytest.fixture
def source_paths(tmp_path,monkeypatch):
    paths={k:ROOT/v for k,v in NAMES.items()}
    if not all(p.exists() for p in paths.values()):pytest.skip('Local reviewed August fixtures unavailable')
    monkeypatch.setattr(store,'ROOT',tmp_path)
    store.init()
    return paths

def test_real_august_migration_and_duplicate(source_paths):
    estimates.save({'period':'2026-08','part':'28957-2JDF0','customer':'현대 울산','price':'131518','reason':'확인된 추정 단가'})
    result=boot.apply(source_paths)
    assert result['record_count']==634
    p=closing.preview('2026-08')
    totals={k:sum(Decimal(r[k]) for r in p['details']) for k in ['opening','receipt','settlement','closing','settlement_amount']}
    assert totals=={'opening':5518,'receipt':112428,'settlement':105925,'closing':12021,'settlement_amount':14712756099}
    row=next(r for r in p['details'] if r['part']=='28957-2JDF0' and r['customer']=='현대 울산')
    assert row['closing']=='7487'
    assert row['closing_amount']=='7487'
    assert row['estimated_closing_amount']=='984675266'
    assert '단가 미정' in row['note']
    special=next(r for r in p['details'] if r['part']=='28991-4C520')
    assert special['customer']=='현대 전주'
    assert special['receipt']=='358' and special['settlement']=='88' and special['closing']=='270'
    assert not p['ready']  # Missing masters must not be silently fabricated.
    assert {i['code'] for i in p['issues']}=={'part','price'}
    assert boot.apply(source_paths)['duplicate']
    assert closing.preview('2026-08')['fingerprint']==p['fingerprint']

def test_validation_failure_leaves_no_business_records(source_paths,monkeypatch):
    original=boot.imports.tables
    def changed(path):
        data=copy.deepcopy(original(path))
        if Path(path)==source_paths['closing']:
            data['현대 전주'][10][4]=89
        return data
    monkeypatch.setattr(boot.imports,'tables',changed)
    with pytest.raises(ValueError):boot.apply(source_paths)
    with store.db() as c:assert c.execute('SELECT COUNT(*) FROM records').fetchone()[0]==0

def test_renamed_inputs_and_nonempty_store_protected(source_paths,tmp_path):
    import shutil
    renamed={}
    for role,path in source_paths.items():
        renamed[role]=tmp_path/(role+'.xlsx');shutil.copy2(path,renamed[role])
    assert boot.build(renamed)['record_count']==634
    boot.apply(source_paths)
    # Different content fingerprint cannot silently replace an initialized month.
    with store.db() as c:c.execute("UPDATE batches SET scope='existing-reviewed-data'")
    with pytest.raises(ValueError,match='초기 이관'):boot.apply(source_paths)
