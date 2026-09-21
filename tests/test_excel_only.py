from catalyst import reports,store
from catalyst.api import app
from fastapi.testclient import TestClient

def test_freeze_requires_only_excel(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path)
    store.init()
    source=tmp_path/'template.xlsx';source.write_bytes(b'fixture')
    requested=[]
    def template(suffix):
        requested.append(suffix)
        assert suffix=='.xlsx'
        return source
    monkeypatch.setattr(reports,'template',template)
    context=reports.freeze_context('2026-08')
    assert requested==['.xlsx']
    assert set(context['templates'])=={'.xlsx'}

def test_ppt_download_hidden_but_file_preserved(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path)
    store.init()
    old=tmp_path/'outputs'/'old.pptx';old.write_bytes(b'old')
    (tmp_path/'outputs'/'current.xlsx').write_bytes(b'xlsx')
    client=TestClient(app)
    assert client.get('/api/outputs').json()==['current.xlsx']
    assert client.get('/api/outputs/old.pptx').status_code==404
    assert old.read_bytes()==b'old'
