import asyncio
import json
import threading
import urllib.request
import urllib.error
import pytest
import re
from ambientlink.app import create_server
from ambientlink.engine import Engine
from ambientlink.settings import validate


def test_local_panel_enforces_host_origin_and_csrf(tmp_path):
    loop=asyncio.new_event_loop()
    thread=threading.Thread(target=loop.run_forever);thread.start()
    server=create_server(tmp_path,loop,Engine(validate({})))
    worker=threading.Thread(target=server.serve_forever);worker.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        assert urllib.request.urlopen(base+'/api/state').status==200
        req=urllib.request.Request(base+'/api/start',data=b'{}',headers={'Origin':base})
        with pytest.raises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
        assert error.value.code==403
        # Account writes use the same CSRF gate and never echo the credentials.
        req=urllib.request.Request(base+'/api/tapo/account',data=b'{"username":"a","password":"secret"}',headers={'Origin':base})
        with pytest.raises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
        assert error.value.code==403
        html=urllib.request.urlopen(base+'/').read().decode()
        token=re.search("const token='([^']+)'",html).group(1)
        req=urllib.request.Request(base+'/api/tapo/account',
            data=b'{"username":"local@example.invalid","password":"test-secret"}',
            headers={'Origin':base,'X-CSRF-Token':token,'Content-Type':'application/json'})
        import sys
        if sys.platform=='win32':
            assert json.load(urllib.request.urlopen(req))=={'ok':True,'configured':True}
            snapshot=urllib.request.urlopen(base+'/api/state').read()
            assert b'test-secret' not in snapshot and b'local@example.invalid' not in snapshot
            assert json.loads(snapshot)['tapoAccountSaved'] is True
        req=urllib.request.Request(base+'/',headers={'Host':'evil.example'})
        with pytest.raises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
        assert error.value.code==403
    finally:
        server.shutdown();worker.join();server.server_close();loop.call_soon_threadsafe(loop.stop);thread.join();loop.close()
