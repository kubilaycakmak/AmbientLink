import asyncio
import time
import pytest
import numpy as np
from ambientlink.colors import screen_colors,dominant
from ambientlink.engine import Engine,smooth
from ambientlink.settings import validate,save,load
from ambientlink.drivers import private_ipv4,GoveeLAN
from ambientlink.govee_ble import encode,decode,AUTH_KEY


def test_color_regions_and_black():
    picture=np.zeros((20,60,3),dtype=np.uint8)
    picture[:,:20]=[255,0,0];picture[:,20:40]=[0,255,0];picture[:,40:]=[0,0,255]
    assert screen_colors(picture)==[(255,0,0),(0,255,0),(0,0,255)]
    assert dominant(np.zeros((20,60,3)))==(0,0,0)
    muted=np.full((20,60,3),[80,76,70]);muted[:1]=[255,0,255]
    assert dominant(muted)==(80,76,70)


def test_black_fade_is_fast_but_normal_cuts_are_bounded():
    old=[(255,255,255)]*3
    step=smooth([(255,0,0)]*3,[(0,0,255)]*3,1/60,.28)
    assert abs(step[0][0]-255)<=8.01
    for _ in range(15):old=smooth(old,[(0,0,0)]*3,1/60,.28)
    assert max(old[0])<1


def test_brightness_has_a_slower_envelope_without_hue_crossfade_dips():
    old=[(25,25,25)]*3
    for _ in range(30):
        new=smooth(old,[(255,255,255)]*3,1/60,.28)
        assert 0<=max(new[0])-max(old[0])<=2.00001
        old=new
    assert max(old[0])<=85.00001
    old=[(255,0,0)]*3
    for _ in range(60):
        old=smooth(old,[(0,0,255)]*3,1/60,.28)
        assert abs(max(old[0])-255)<.0001


def test_config_validation_and_persistence(tmp_path):
    config=validate({'devices':[{'driver':'govee-h600b','address':'AA:BB:CC:DD:EE:FF'}]})
    save(tmp_path/'settings.json',config);assert load(tmp_path/'settings.json')==config
    for bad in ({'fps':True},{'devices':[{'driver':'other','address':'whatever'}]},
                {'devices':[{'driver':'govee-lan','address':'8.8.8.8'}]},
                {'devices':[{'driver':'govee-lan','address':'192.168.1.5','gains':[float('nan'),1,1]}]},
                {'devices':config['devices']*2}):
        with pytest.raises(ValueError):validate(bad)
    with pytest.raises(ValueError):private_ipv4('127.0.0.1')


def test_h600b_public_handshake_and_packet_integrity():
    packet=bytes.fromhex('9e6122db157166686c5d658a2de1cdfbc9202c8e')
    plain=decode(packet,AUTH_KEY)
    assert plain[:2]==b'\xe7\x01'
    assert encode(plain[:19],AUTH_KEY)==packet
    with pytest.raises(ValueError):decode(packet[:-1]+bytes([packet[-1]^1]),AUTH_KEY)


def test_lan_black_power_and_duplicate_suppression():
    async def run():
        d=GoveeLAN({'address':'192.168.1.5'});commands=[]
        async def record(cmd,data):commands.append((cmd,data))
        d.command=record
        try:
            await d.send((255,0,0),60)
            assert commands[-1]==('turn',{'value':1})
            assert not await d.send((255,0,0),60)
            await d.send((0,0,0),60)
            assert commands[-1]==('turn',{'value':0})
        finally:await d.close()
    asyncio.run(run())


def test_slow_device_does_not_stall_capture_or_accumulate_queue():
    class Device:
        rate=30
        def __init__(self,spec):self.spec=spec;self.colors=[];self.closed=False
        async def connect(self):pass
        async def send(self,rgb,brightness):
            if self.spec['name']=='slow':await asyncio.sleep(.08)
            self.colors.append(rgb);return True
        async def close(self,restore=True):self.closed=restore
    class Capture:
        def __enter__(self):return self
        def colors(self,mode):return [(100,50,20)]*3
        def __exit__(self,*a):pass
    async def run():
        config=validate({'devices':[{'driver':'govee-h600b','address':f'AA:BB:CC:DD:EE:0{i}','name':name,'enabled':i==0} for i,name in enumerate(('fast','slow'))]})
        e=Engine(config,{'govee-h600b':Device},Capture)
        await e.start();await asyncio.sleep(.5)
        clients=list(e.clients)
        assert e.state['frames']>15 and e.state['error'] is None
        assert len(clients[0].colors)>len(clients[1].colors)
        assert all(c==(0,0,0) for c in clients[1].colors)
        await e.stop();assert all(c.closed for c in clients)
    asyncio.run(run())
