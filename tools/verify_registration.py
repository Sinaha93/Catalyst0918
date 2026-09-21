"""Smoke-test a windowed build against a disposable database, never live data."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from catalyst import imports, store


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('executable',type=Path)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='catalyst_registration_') as tmp:
        store.ROOT=Path(tmp);store.init()
        path=store.ROOT/'test.csv';path.write_text('품번,수량\nTEST,2',encoding='utf-8')
        sid=imports.register(path)['id']
        imports.commit_rows([{'kind':'receipt','part':'TEST','customer':'시험','date':'2026-08-01','quantity':2}],sid,'smoke','append')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        proc=subprocess.Popen([str(args.executable.resolve()),'--no-browser','--port',str(port)],env={**os.environ,'CATALYST_HOME':tmp},creationflags=subprocess.CREATE_NO_WINDOW)
        def call(route,payload=None):
            req=Request(f'http://127.0.0.1:{port}'+route,data=json.dumps(payload).encode() if payload is not None else None,headers={'Content-Type':'application/json'})
            with urlopen(req,timeout=5) as response:return response.read()
        try:
            for _ in range(100):
                try:call('/api/status');break
                except OSError:
                    if proc.poll() is not None:raise RuntimeError('Build exited before startup')
                    time.sleep(.2)
            else:raise RuntimeError('Startup timeout')
            assert b'/assets/' in call('/')
            for expected in (0,1):
                impact=json.loads(call(f'/api/sources/{sid}/impact'))
                call(f'/api/sources/{sid}/cancel-or-restore',{'fingerprint':impact['fingerprint'],'reason':'격리 실행 시험'})
                assert len(json.loads(call('/api/records')))==expected
            call('/api/shutdown',{})
            proc.wait(timeout=15)
            assert proc.returncode==0
            print('PASS: windowed executable, frontend serving, cancellation, restoration and clean shutdown')
        finally:
            if proc.poll() is None:proc.terminate();proc.wait(timeout=15)


if __name__=='__main__':main()
