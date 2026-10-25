"""One latest-frame sender per device: slow radios never build a frame queue."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time
import math
from collections import deque
from .drivers import REGISTRY
from .color_smoothing import LinearLightSmoother
from .diagnostics import Diagnostics, error_fields


async def pace(start,rate):
    # Recheck the monotonic deadline: Windows event loops can wake timers early.
    deadline=start+1/rate
    while (remaining:=deadline-time.perf_counter())>0:
        await asyncio.sleep(remaining)
    await asyncio.sleep(0)


class Engine:
    def __init__(self,settings,drivers=None,capture=None,diagnostics=None):
        self.settings=settings;self.registry=drivers or REGISTRY;self.capture_factory=capture
        self.diagnostics=diagnostics or Diagnostics()
        self.lock=asyncio.Lock();self.task=None;self.clients=[];self.latest=None
        self.device_latest=None;self.latest_at=None
        self.state={'active':False,'mode':'idle','fps':0,'frames':0,'error':None,'devices':[],'colors':[[0,0,0]]*3}

    async def stop(self,restore=True):
        if self.task:
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True);self.task=None
        results=await asyncio.gather(*(client.close(restore) for client in self.clients),return_exceptions=True)
        self.clients=[];self.latest=None;self.device_latest=None;self.latest_at=None
        self.state.update(active=False,mode='idle',fps=0)
        for row in self.state['devices']:row.update(connected=False,updateFps=0,frameAgeMs=None)
        if any(isinstance(r,Exception) for r in results):self.state['error']='Some devices could not restore; check them manually'
        for index,result in enumerate(results):
            if isinstance(result,Exception):self.diagnostics.record('error',light=index+1,phase='restore',**error_fields(result,'restore_failure'))
        self.diagnostics.record('stop')

    async def configure(self,value):
        identity=lambda settings:[(d['driver'],d['address']) for d in settings['devices']]
        if identity(value)!=identity(self.settings):
            await self.stop()
            self.state['devices']=[]
        self.settings=value
        self.diagnostics.record('settings_changed')
        for client,spec in zip(self.clients,value['devices']):client.spec=spec

    async def pause_stream(self):
        if self.task:
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True);self.task=None
        self.latest=None;self.device_latest=None;self.latest_at=None

    def prepare(self):
        if not self.settings['devices']:raise ValueError('Add at least one supported light first')
        self.clients=[self.registry[s['driver']](s) for s in self.settings['devices']]
        self.state['devices']=[{'name':s['name'],'connected':False,'error':None,'writes':0,'outputRgb':[0,0,0],
                               'rateLimitHz':c.rate,'connections':0,'errors':0,'timeouts':0,'deduplicated':0,
                               'transport':getattr(c,'transport','BLE acknowledged' if s['driver']=='govee-h600b' else 'UDP unconfirmed')} for s,c in zip(self.settings['devices'],self.clients)]

    async def start(self):
        if self.task and not self.task.done() and self.state['mode']=='screen':return
        await self.pause_stream()
        if not self.clients:self.prepare()
        self.state.update(active=True,mode='screen',error=None,frames=0)
        self.diagnostics.record('start')
        self.task=asyncio.create_task(self.stream())

    async def manual(self,rgb=None):
        if self.state['mode']!='manual':await self.pause_stream()
        if not self.clients:self.prepare()
        color=rgb or self.settings['rgb'];self.latest=[color]*3
        self.state.update(active=False,mode='manual',error=None,fps=0,colors=self.latest)
        self.diagnostics.record('manual')
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
        updates=deque();latencies=deque(maxlen=120);last_success=None
        while True:
            tick=time.perf_counter()
            phase='connect'
            operation_at=tick
            try:
                spec=self.settings['devices'][index]
                if not connected:
                    connect_at=time.perf_counter()
                    await client.connect();connected=True;row.update(connected=True,error=None)
                    row['connections']+=1;row['connectMs']=round((time.perf_counter()-connect_at)*1000,1)
                    self.diagnostics.record('connected',light=index+1,durationMs=row['connectMs'])
                if self.latest is not None:
                    sampled_at=self.latest_at
                    if self.state['mode']=='screen' and self.device_latest is not None:
                        rgb=self.device_latest[index]
                    else:
                        rgb=self.latest[spec['zone']]
                        rgb=tuple(max(0,min(255,round(c*g))) for c,g in zip(rgb,spec['gains']))
                    if not spec['enabled']:rgb=(0,0,0)
                    send_at=time.perf_counter()
                    operation_at=send_at
                    phase='send'
                    if await client.send(rgb,self.settings['brightness']):
                        row['writes']+=1
                        now=time.perf_counter();updates.append(now)
                        row['sendMs']=round((now-send_at)*1000,1)
                        row['frameAgeMs']=round((now-sampled_at)*1000,1) if sampled_at is not None else None
                        last_success=now;latencies.append(row['sendMs']);ordered=sorted(latencies)
                        row.update(sendSamples=len(ordered),sendP50Ms=ordered[(len(ordered)-1)//2],
                                   sendP95Ms=ordered[max(0,math.ceil(len(ordered)*.95)-1)],sendMaxMs=ordered[-1])
                    else:row['deduplicated']+=1
                    row['outputRgb']=list(rgb)
                now=time.perf_counter()
                while updates and now-updates[0]>3:updates.popleft()
                row['updateFps']=round(len(updates)/3,1)
                row['lastSuccessAgeMs']=round((now-last_success)*1000,1) if last_success is not None else None
                # H600B idle sessions need a bounded heartbeat, even on a static scene.
                if hasattr(client,'bulb') and tick>check_at:
                    phase='heartbeat'
                    operation_at=time.perf_counter()
                    row['power']=await client.bulb.read_power();check_at=time.perf_counter()+5
                failures=0
                row['consecutiveErrors']=0
                await pace(tick,client.rate)
            except asyncio.CancelledError:raise
            except Exception as error:
                connected=False;failures+=1;updates.clear();row.update(connected=False,error=str(error)[:180],updateFps=0)
                fields=error_fields(error,'device_failure')
                row['errors']+=1;row['consecutiveErrors']=failures
                row['errorCode']=fields['code'];row['errorCategory']=fields['category']
                if fields['category']=='timeout':row['timeouts']+=1
                self.diagnostics.record('error',light=index+1,phase=phase,retryInSeconds=min(10,failures),
                                        durationMs=round((time.perf_counter()-operation_at)*1000,1),**fields)
                try:await client.close(False)
                except Exception:pass  # A failed disconnect must not disable reconnects.
                await asyncio.sleep(min(10,failures))

    async def stream(self):
        tasks=[asyncio.create_task(self.sender(i)) for i in range(len(self.clients))]
        loop=asyncio.get_running_loop();manager=None;entered=False;last=time.perf_counter();frames=0;since=last
        smoothers=[LinearLightSmoother(self.settings['smoothing']/1000,spec['gamma']) for spec in self.settings['devices']]
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
                self.state['captureMs']=round((time.perf_counter()-tick)*1000,1)
                outputs=[]
                for i,spec in enumerate(self.settings['devices']):
                    if smoothers[i].corrected!=spec['gamma']:
                        smoothers[i]=LinearLightSmoother(corrected=spec['gamma'])
                    smoothers[i].tau=self.settings['smoothing']/1000
                    target=tuple(max(0,min(255,round(c*g))) for c,g in zip(current[spec['zone']],spec['gains']))
                    value=smoothers[i].update([target],tick-last)[0]
                    outputs.append(tuple(round(v) for v in value))
                last=tick
                self.latest=[tuple(c) for c in current]
                self.device_latest=outputs;self.latest_at=tick
                self.state['colors']=self.latest;frames+=1;self.state['frames']+=1
                if tick-since>=1:self.state['fps']=round(frames/(tick-since),1);since=tick;frames=0
                await pace(tick,self.settings['fps'])
        except asyncio.CancelledError:raise
        except Exception as error:
            self.state.update(error=str(error)[:250],active=False,mode='error',fps=0)
            self.diagnostics.record('error',phase='capture',**error_fields(error,'capture_failure'))
        finally:
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            if entered:await loop.run_in_executor(executor,manager.__exit__,None,None,None)
            executor.shutdown(wait=True)
            if self.state['mode']=='error':
                await asyncio.gather(*(c.close(True) for c in self.clients),return_exceptions=True)
                for row in self.state['devices']:row.update(connected=False,updateFps=0,frameAgeMs=None)
