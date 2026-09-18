"""Packaged app smoke test in a separate temporary data directory."""
import os
import subprocess
import tempfile
import time
from pathlib import Path
import httpx

root=Path(__file__).resolve().parents[1]
home=Path(tempfile.mkdtemp(prefix='catalyst_exe_verify_'))
env={**os.environ,'CATALYST_HOME':str(home)}
url='http://127.0.0.1:18765'
log=(home/'server.log').open('w',encoding='utf-8')

def start():
    process=subprocess.Popen([str(root/'촉매마감관리.exe'),'--no-browser','--port','18765'],env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(150):
        if process.poll() is not None:raise RuntimeError('Executable exited; see '+str(home/'server.log'))
        try:
            if httpx.get(url+'/api/status').status_code==200:return process
        except httpx.HTTPError:pass
        time.sleep(.2)
    process.terminate()
    raise TimeoutError('Server start timed out')

process=start()
try:
    assert httpx.get(url).status_code==200
    rows=[]
    for kind,extra in [('part',{}),('price',{'price':'100'}),('opening',{'quantity':'2','amount':'200'}),('receipt',{'quantity':'10'}),('settlement',{'quantity':'7'}),('plan',{'quantity':'8','amount':'800'})]:
        rows.append({'kind':kind,'part':'EXE-TEST','customer':'기아 화성','date':'2026-08-01',**extra})
    response=httpx.post(url+'/api/records',json={'rows':rows,'scope':'exe-test','reason':'격리된 실행 파일 검증'})
    response.raise_for_status()
    p=httpx.get(url+'/api/closing/2026-08').json()
    assert p['ready'],p
    run=httpx.post(url+'/api/closing/2026-08',json={'fingerprint':p['fingerprint']}).json()
    assert 'id' in run,run
    job=httpx.post(url+f'/api/runs/{run["id"]}/export',json={}).json()
    for _ in range(180):
        state=httpx.get(url+'/api/jobs/'+job['job_id']).json()
        if state['state']!='running':break
        time.sleep(.5)
    assert state['state']=='done',state
    assert len(httpx.get(url+'/api/outputs').json())==2
    httpx.post(url+'/api/shutdown',json={}).raise_for_status()
    process.wait(timeout=20)
    process=start()
    assert httpx.get(url+'/api/status').json()['records']==6
    assert len(httpx.get(url+'/api/runs').json())==1
    print('Packaged UI/API, calculation, Office export and restart persistence verified',flush=True)
    print(home,flush=True)
finally:
    if process.poll() is None:
        try:
            httpx.post(url+'/api/shutdown',json={}).raise_for_status()
            process.wait(timeout=20)
        except Exception:
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    log.close()
