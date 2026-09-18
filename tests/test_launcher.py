import logging
import sys
import uvicorn
from catalyst import store
from launcher import configure_logging

def test_logging_without_console(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path)
    logger=logging.getLogger('uvicorn')
    previous=(logger.handlers[:],logger.level,logger.propagate)
    children={n:(logging.getLogger(n).handlers[:],logging.getLogger(n).propagate) for n in ('uvicorn.error','uvicorn.access')}
    try:
        configure_logging()
        monkeypatch.setattr(sys,'stdout',None)
        monkeypatch.setattr(sys,'stderr',None)
        config=uvicorn.Config('catalyst.api:app',log_config=None)
        config.load()
        logging.getLogger('uvicorn.error').info('windowless test')
        logger.handlers[0].flush()
        assert 'windowless test' in (tmp_path/'logs'/'application.log').read_text(encoding='utf-8')
    finally:
        for handler in logger.handlers:
            if handler not in previous[0]:handler.close()
        logger.handlers,logger.level,logger.propagate=previous
        for n,(handlers,propagate) in children.items():
            logging.getLogger(n).handlers=handlers
            logging.getLogger(n).propagate=propagate
