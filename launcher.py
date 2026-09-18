import argparse
import threading
import webbrowser
import socket
import json
from urllib.request import urlopen
import uvicorn
from catalyst import store

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    store.init()
    port=args.port
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',port))==0:
            try:
                with urlopen(f'http://127.0.0.1:{port}/api/status',timeout=2) as response:
                    if json.load(response).get('app')!='catalyst-closing':raise ValueError('다른 프로그램이 사용 중인 포트입니다')
            except Exception as exc:
                raise RuntimeError(f'{port} 포트를 사용할 수 없습니다. --port 옵션으로 다른 포트를 지정해주세요') from exc
            if not args.no_browser: webbrowser.open(f'http://127.0.0.1:{port}')
            return
    if not args.no_browser:
        threading.Timer(1.5,lambda:webbrowser.open(f'http://127.0.0.1:{port}')).start()
    from catalyst.api import app
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port))
    app.state.shutdown=lambda:setattr(server,'should_exit',True)
    server.run()

if __name__=='__main__': main()
