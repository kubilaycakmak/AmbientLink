"""One latest-frame sender per device: slow radios never build a frame queue."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import math
import time
from .drivers import REGISTRY


async def pace(start,rate):
    # Recheck the monotonic deadline: Windows event loops can wake timers early.
    deadline=start+1/rate
    while (remaining:=deadline-time.perf_counter())>0:
        await asyncio.sleep(remaining)
    await asyncio.sleep(0)


def smooth(previous,current,dt,tau):
    if previous is None:return [tuple(c) for c in current]
    dt=min(.1,max(0,dt));result=[]
    for old,new in zip(previous,current):
        dark=max(new)<=5;alpha=1-math.exp(-dt/(.035 if dark else tau))
        delta=[(b-a)*alpha for a,b in zip(old,new)];limit=(4000 if dark else 480)*dt
        scale=min(1,limit/max(map(abs,delta))) if any(delta) else 1
        value=tuple(a+d*scale for a,d in zip(old,delta))
        result.append(tuple(new) if dark and max(abs(a-b) for a,b in zip(value,new))<.5 else value)
    return result


class Engine:
    def __init__(self,settings,drivers=None,capture=None):
        self.settings=settings;self.registry=drivers or REGISTRY;self.capture_factory=capture
        self.lock=asyncio.Lock();self.task=None;self.clients=[];self.latest=None
        self.state={'active':False,'mode':'idle','fps':0,'frames':0,'error':None,'devices':[],'colors':[[0,0,0]]*3}

    async def stop(self,restore=True):
        if self.task:
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True);self.task=None
        results=await asyncio.gather(*(client.close(restore) for client in self.clients),return_exceptions=True)
        self.clients=[];self.latest=None
        self.state.update(active=False,mode='idle',fps=0)
        if any(isinstance(r,Exception) for r in results):self.state['error']='Some devices could not restore; check them manually'

    async def configure(self,value):
        identity=lambda settings:[(d['driver'],d['address']) for d in settings['devices']]
        if identity(value)!=identity(self.settings):
            await self.stop()
            self.state['devices']=[]
        self.settings=value
        for client,spec in zip(self.clients,value['devices']):client.spec=spec

    async def pause_stream(self):
        if self.task:
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True);self.task=None
        self.latest=None

    def prepare(self):
        if not self.settings['devices']:raise ValueError('Add at least one supported light first')
        self.clients=[self.registry[s['driver']](s) for s in self.settings['devices']]
        self.state['devices']=[{'name':s['name'],'connected':False,'error':None,'writes':0,'outputRgb':[0,0,0],
                               'transport':'BLE acknowledged' if s['driver']=='govee-h600b' else 'UDP unconfirmed'} for s in self.settings['devices']]

    async def start(self):
        if self.task and not self.task.done() and self.state['mode']=='screen':return
        await self.pause_stream()
        if not self.clients:self.prepare()
        self.state.update(active=True,mode='screen',error=None,frames=0)
        self.task=asyncio.create_task(self.stream())

    async def manual(self,rgb=None):
        if self.state['mode']!='manual':await self.pause_stream()
        if not self.clients:self.prepare()
        color=rgb or self.settings['rgb'];self.latest=[color]*3
        self.state.update(active=False,mode='manual',error=None,fps=0,colors=self.latest)
        # Retain connections for keepalive and restore when stopping.
        if not self.task or self.task.done():self.task=asyncio.create_task(self.manual_loop())

    async def manual_loop(self):
        tasks=[asyncio.create_task(self.sender(i)) for i in range(len(self.clients))]
        try:await asyncio.gather(*tasks)
        finally:
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)

    async def sender(self,index):
        client=self.clients[index];row=self.state['devices'][index]
        connected=False;failures=0;check_at=0
        while True:
            tick=time.perf_counter()
            try:
                spec=self.settings['devices'][index]
                if not connected:
                    await client.connect();connected=True;row.update(connected=True,error=None)
                if self.latest is not None:
                    rgb=self.latest[spec['zone']]
                    rgb=tuple(max(0,min(255,round(c*g))) for c,g in zip(rgb,spec['gains']))
                    if not spec['enabled']:rgb=(0,0,0)
                    if await client.send(rgb,self.settings['brightness']):row['writes']+=1
                    row['outputRgb']=list(rgb)
                # H600B idle sessions need a bounded heartbeat, even on a static scene.
                if hasattr(client,'bulb') and tick>check_at:
                    row['power']=await client.bulb.read_power();check_at=time.perf_counter()+5
                failures=0
                await pace(tick,client.rate)
            except asyncio.CancelledError:raise
            except Exception as error:
                connected=False;failures+=1;row.update(connected=False,error=str(error)[:180])
                try:await client.close(False)
                except Exception:pass  # A failed disconnect must not disable reconnects.
                await asyncio.sleep(min(10,failures))

    async def stream(self):
        tasks=[asyncio.create_task(self.sender(i)) for i in range(len(self.clients))]
        loop=asyncio.get_running_loop();manager=None;entered=False;previous=None;last=time.perf_counter();frames=0;since=last
        executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='capture')
        try:
            if self.capture_factory:manager=self.capture_factory()
            else:
                from .capture import PrimaryCapture
                manager=PrimaryCapture()
            camera=await loop.run_in_executor(executor,manager.__enter__)
            entered=True
            while True:
                tick=time.perf_counter()
                current=await loop.run_in_executor(executor,camera.colors,self.settings['mode'])
                previous=smooth(previous,current,tick-last,self.settings['smoothing']/1000);last=tick
                self.latest=[tuple(round(v) for v in color) for color in previous]
                self.state['colors']=self.latest;frames+=1;self.state['frames']+=1
                if tick-since>=1:self.state['fps']=round(frames/(tick-since),1);since=tick;frames=0
                await pace(tick,self.settings['fps'])
        except asyncio.CancelledError:raise
        except Exception as error:self.state.update(error=str(error)[:250],active=False,mode='error',fps=0)
        finally:
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            if entered:await loop.run_in_executor(executor,manager.__exit__,None,None,None)
            executor.shutdown(wait=True)
            if self.state['mode']=='error':
                await asyncio.gather(*(c.close(True) for c in self.clients),return_exceptions=True)
