from catalyst import imports

def test_baseline_accepts_old_and_new_trend_names(monkeypatch,tmp_path):
    for name in ('종합2','월별 계획·실적'):
        monkeypatch.setattr(imports,'tables',lambda path,n=name:{'종합':[],n:[]})
        assert imports.inspect(tmp_path/'reference.csv')['type']=='월마감 기준자료'
