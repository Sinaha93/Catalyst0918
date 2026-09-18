"""Run an isolated Office export with synthetic input, never production records."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from catalyst import store, imports, closing, reports

original=store.ROOT
store.ROOT=Path(tempfile.mkdtemp(prefix='catalyst_verify_'))
store.init()
reports.template=lambda suffix:next(original.glob('*촉매 마감'+suffix))
rows=[]
count=70 if '--many' in sys.argv else 1
for i in range(count):
    for kind,extra in [('part',{}),('price',{'price':'100'}),('opening',{'quantity':'2','amount':'200'}),('receipt',{'quantity':'10'}),('settlement',{'quantity':'7'}),('plan',{'quantity':'8','amount':'800'})]:
        rows.append({'kind':kind,'part':f'TEST-{i+1:03}','customer':'기아 화성','date':'2026-08-01',**extra})
imports.commit_rows(rows,None,'synthetic','append','격리된 출력 검증')
p=closing.preview('2026-08')
rid=closing.finalize('2026-08',p['fingerprint'])['id']
print(reports.generate(rid),flush=True)
print(store.ROOT,flush=True)
