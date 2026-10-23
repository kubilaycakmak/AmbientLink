import asyncio
import copy

from ambientlink import engine
from ambientlink.settings import validate


def test_pacing_rechecks_deadline_after_early_windows_timer(monkeypatch):
    clock=[10.0];waits=[]
    async def early_sleep(delay):
        waits.append(delay)
        clock[0]+=min(delay,.003)
    monkeypatch.setattr(engine.time,'perf_counter',lambda:clock[0])
    monkeypatch.setattr(engine.asyncio,'sleep',early_sleep)
    asyncio.run(engine.pace(10.0,60))
    assert clock[0]>=10+1/60
    assert len(waits)>3  # A single early wake must not send another frame.


def test_live_controls_do_not_restore_or_disconnect_other_lights():
    class Device:
        rate=30
        def __init__(self,spec):self.spec=spec;self.colors=[];self.closes=[]
        async def connect(self):pass
        async def send(self,rgb,brightness):self.colors.append(rgb);return True
        async def close(self,restore=True):self.closes.append(restore)
    class Capture:
        def __enter__(self):return self
        def colors(self,mode):return [(100,20,10)]*3
        def __exit__(self,*args):pass
    async def run():
        settings=validate({'devices':[{'driver':'govee-h600b','address':f'AA:BB:CC:DD:EE:0{i}'} for i in range(2)]})
        e=engine.Engine(settings,{'govee-h600b':Device},Capture)
        try:
            await e.start();await asyncio.sleep(.12)
            clients=list(e.clients);task=e.task
            value=copy.deepcopy(settings);value['devices'][0]['enabled']=False
            value['devices'][1]['zone']=2;value['brightness']=40
            await e.configure(value);await e.start();await asyncio.sleep(.12)
            assert e.task is task and e.clients==clients
            assert clients[0].colors[-1]==(0,0,0)
            assert clients[1].colors[-1]==(100,20,10)
            await e.manual([0,100,0]);await asyncio.sleep(.12)
            assert clients[1].colors[-1]==(0,100,0)
            await e.start();await asyncio.sleep(.12)
            assert e.clients==clients and all(not c.closes for c in clients)
        finally:await e.stop()
        assert all(c.closes==[True] for c in clients)
        assert all(not d['connected'] and d['updateFps']==0 for d in e.state['devices'])
    asyncio.run(run())


def test_mixed_gamma_gains_and_live_transition_settings_keep_independent_outputs():
    class Device:
        rate=30
        def __init__(self,spec):self.spec=spec;self.colors=[]
        async def connect(self):pass
        async def send(self,rgb,brightness):
            changed=not self.colors or self.colors[-1]!=rgb
            self.colors.append(rgb)
            return changed
        async def close(self,restore=True):pass
    class Capture:
        value=(128,101,56)
        def __enter__(self):return self
        def colors(self,mode):return [self.value]*3
        def __exit__(self,*args):pass
    async def run():
        settings=validate({'smoothing':350,'devices':[
            {'driver':'govee-h600b','address':'AA:BB:CC:DD:EE:01','gamma':True},
            {'driver':'govee-lan','address':'192.0.2.5','gamma':False,'gains':[.5,1,1]},
        ]})
        e=engine.Engine(settings,{'govee-h600b':Device,'govee-lan':Device},Capture)
        try:
            await e.start();await asyncio.sleep(.1)
            assert e.clients[0].colors[-1]==(128,101,56)
            assert e.clients[1].colors[-1]==(64,101,56)
            Capture.value=(30,80,120)
            await asyncio.sleep(.55)
            assert e.clients[0].colors[-1]==(30,80,120)
            assert e.clients[1].colors[-1]==(15,80,120)
            task=e.task
            settings=copy.deepcopy(settings);settings['smoothing']=150;settings['fps']=30
            settings['devices'][1]['gamma']=True
            await e.configure(settings)
            Capture.value=(35,35,35)
            await asyncio.sleep(.55)
            assert e.task is task
            assert e.clients[1].colors[-1]==(18,35,35)
            assert e.state['devices'][0]['frameAgeMs']>=0
            assert e.state['devices'][0]['updateFps']>=0
        finally:await e.stop()
    asyncio.run(run())
