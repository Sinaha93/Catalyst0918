import argparse
import threading
import webbrowser
import socket
import json
import sys
import logging
from logging.handlers import RotatingFileHandler
from urllib.request import urlopen
import uvicorn
from catalyst import store

def configure_logging():
    folder=store.ROOT/'logs'
    folder.mkdir(parents=True,exist_ok=True)
    handler=RotatingFileHandler(folder/'application.log',maxBytes=2*1024*1024,backupCount=3,encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    logger=logging.getLogger('uvicorn')
    logger.handlers=[handler]
    logger.setLevel(logging.INFO)
    logger.propagate=False
    for name in ('uvicorn.error','uvicorn.access'):
        child=logging.getLogger(name)
        child.handlers=[]
        child.propagate=True
    return logger

def main():
    configure_logging()
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
    # Windowed executables have no stdout/stderr. Never install Uvicorn's
    # default console formatter, which can call isatty() on a missing stream.
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_config=None))
    app.state.shutdown=lambda:setattr(server,'should_exit',True)
    server.run()

if __name__=='__main__':
    try:
        main()
    except Exception:
        logging.getLogger('uvicorn').exception('프로그램 시작 실패')
        if sys.platform=='win32' and (getattr(sys,'frozen',False) or sys.stderr is None):
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,'프로그램을 시작하지 못했습니다.\nlogs/application.log를 확인해주세요.','촉매 마감 관리',0x10)
        else:
            raise
