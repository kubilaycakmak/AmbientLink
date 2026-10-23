"""Portable Windows launcher and loopback-only control panel."""
import asyncio
import copy
import ctypes
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import webbrowser
from . import __version__
from . import settings
from .drivers import discover
from .engine import Engine


def run_loop(loop):
    sys.coinit_flags=0
    ole=ctypes.OleDLL('ole32');ole.CoInitializeEx(None,0)
    try:asyncio.set_event_loop(loop);loop.run_forever()
    finally:ole.CoUninitialize()


def create_server(root,loop,engine):
    token=secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def setup(self):super().setup();self.connection.settimeout(10)
        def reply(self,code,data,kind='application/json'):
            raw=json.dumps(data,allow_nan=False).encode() if kind=='application/json' else data
            self.send_response(code);self.send_header('Content-Type',kind+'; charset=utf-8')
            self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store')
            self.send_header('X-Frame-Options','DENY');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            try:self.wfile.write(raw)
            except OSError:pass
        def local(self):return self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}'
        def do_GET(self):
            if not self.local():return self.reply(403,{'error':'Local access only'})
            if self.path=='/':
                html=Path(__file__).with_name('panel.html').read_text(encoding='utf-8').replace('__TOKEN__',token).replace('__VERSION__',__version__)
                return self.reply(200,html.encode(),'text/html')
            if self.path=='/api/state':
                # Retrieve a consistent snapshot on the controller loop.
                async def snapshot():return {'settings':copy.deepcopy(engine.settings),'state':copy.deepcopy(engine.state)}
                future=asyncio.run_coroutine_threadsafe(snapshot(),loop)
                return self.reply(200,future.result(timeout=3))
            self.reply(404,{'error':'Not found'})
        def do_POST(self):
            origin=f'http://127.0.0.1:{self.server.server_port}'
            if not self.local() or self.headers.get('Origin')!=origin or not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),token):
                return self.reply(403,{'error':'Origin or request token rejected'})
            if self.headers.get('Transfer-Encoding'):return self.reply(400,{'error':'Invalid request'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=65536:raise ValueError('Request too large')
                body=json.loads(self.rfile.read(size))
                if not isinstance(body,dict):raise ValueError('Invalid request')
                async def command():
                    async with engine.lock:
                        if self.path=='/api/discover':return await discover()
                        if self.path=='/api/settings':
                            value=settings.validate(body)
                            await engine.configure(value)
                            settings.save(root/'settings.json',value)
                            return {'ok':True}
                        if self.path=='/api/start':await engine.start()
                        elif self.path=='/api/manual':await engine.manual()
                        elif self.path=='/api/off':await engine.manual([0,0,0])
                        elif self.path=='/api/stop':await engine.stop()
                        elif self.path=='/api/quit':
                            await engine.stop();threading.Thread(target=self.server.shutdown,daemon=True).start()
                        else:raise ValueError('Unknown action')
                        return {'ok':True}
                future=asyncio.run_coroutine_threadsafe(command(),loop)
                result=future.result(timeout=60)
                self.reply(200,result)
            except Exception as error:self.reply(400,{'error':str(error)[:240]})
    return ThreadingHTTPServer(('127.0.0.1',0),Handler)


def main():
    if sys.platform!='win32':raise SystemExit('AmbientLink currently supports Windows 10/11 only')
    root=Path(os.environ.get('AMBIENTLINK_DATA_DIR',str(Path(os.environ['LOCALAPPDATA'])/'AmbientLink')))
    root.mkdir(parents=True,exist_ok=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p];kernel.CreateMutexW.restype=ctypes.c_void_p
    mutex=kernel.CreateMutexW(None,False,'Local\\AmbientLink')
    if ctypes.get_last_error()==183:
        try:
            port=json.loads((root/'instance.json').read_text())['port']
            if type(port)is int and 1024<=port<=65535:webbrowser.open(f'http://127.0.0.1:{port}/')
        except (OSError,ValueError,KeyError):pass
        return
    loop=asyncio.new_event_loop();loop.time=__import__('time').perf_counter
    loop._clock_resolution=__import__('time').get_clock_info('perf_counter').resolution
    thread=threading.Thread(target=run_loop,args=(loop,),daemon=True);thread.start()
    try:
        config=settings.load(root/'settings.json');engine=Engine(config)
        server=create_server(root,loop,engine)
        (root/'instance.json').write_text(json.dumps({'port':server.server_port}))
        if '--no-browser' not in sys.argv:webbrowser.open(f'http://127.0.0.1:{server.server_port}/')
        try:server.serve_forever(poll_interval=.2)
        finally:
            asyncio.run_coroutine_threadsafe(engine.stop(),loop).result(timeout=30)
            server.server_close()
    except Exception as error:
        (root/'last-error.txt').write_text(type(error).__name__+': '+str(error))
        ctypes.windll.user32.MessageBoxW(None,str(error),'AmbientLink could not start',0x10)
    finally:
        (root/'instance.json').unlink(missing_ok=True)
        loop.call_soon_threadsafe(loop.stop);thread.join(timeout=5)
        if mutex:kernel.CloseHandle(ctypes.c_void_p(mutex))
