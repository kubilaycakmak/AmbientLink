import asyncio
from types import SimpleNamespace
import pytest
from ambientlink.tapo_driver import TapoL530
from ambientlink.credentials import Credentials
from ambientlink.settings import validate


class Account:
    def read(self):return {'username':'local@example.invalid','password':'test-secret'}


class Request:
    def __init__(self):self.values={}
    def on(self):self.values['on']=True;return self
    def off(self):self.values['on']=False;return self
    def brightness(self,value):assert 1<=value<=100;self.values['brightness']=value;return self
    def color_temperature(self,value):self.values['temperature']=value;return self
    def hue_saturation(self,hue,saturation):
        assert 0<=hue<=360 and 1<=saturation<=100
        self.values.update(hue=hue,saturation=saturation);return self
    async def send(self,device):device.sent.append(self.values)


class Device:
    def __init__(self):
        self.sent=[]
        self.info=SimpleNamespace(model='L530E',dynamic_light_effect_enable=False,
            device_on=False,brightness=37,color_temp=2700,hue=0,saturation=100)
    async def get_device_info(self):return self.info
    def set(self):return Request()


def adapter(device):
    class Client:
        def __init__(self,*args,**kwargs):pass
        async def l530(self,address):return device
    return TapoL530({'address':'192.168.1.50'},Account(),Client)


def test_tapo_atomic_color_dim_power_deduplication_and_restore():
    async def run():
        device=Device();driver=adapter(device)
        await driver.connect()
        assert await driver.send((128,0,0),60)
        assert device.sent[-1]=={'hue':0,'saturation':100,'brightness':30,'on':True}
        assert not await driver.send((128,0,0),60)
        await driver.send((0,0,0),60);assert device.sent[-1]=={'on':False}
        await driver.send((26,26,26),100)
        assert device.sent[-1]=={'temperature':6500,'brightness':10,'on':True}
        await driver.close()
        assert device.sent[-1]=={'temperature':2700,'brightness':37,'on':False}
    asyncio.run(run())


def test_tapo_reconnect_keeps_original_and_errors_do_not_expose_credentials():
    async def run():
        device=Device();driver=adapter(device)
        await driver.connect();await driver.close(False)
        device.info.brightness=100
        await driver.connect();await driver.close()
        assert device.sent[-1]['brightness']==37
        async def fail():raise RuntimeError('test-secret local@example.invalid')
        device.get_device_info=fail
        with pytest.raises(ValueError) as error:await driver.connect()
        assert 'test-secret' not in str(error.value) and '@' not in str(error.value)
    asyncio.run(run())


@pytest.mark.parametrize('model,effect',[('P110',False),('L530E',True)])
def test_wrong_model_and_unrestorable_effect_rejected_before_writing(model,effect):
    async def run():
        device=Device();device.info.model=model;device.info.dynamic_light_effect_enable=effect
        with pytest.raises(ValueError):await adapter(device).connect()
        assert not device.sent
    asyncio.run(run())


def test_windows_credentials_encrypted_and_separate_from_settings(tmp_path):
    import sys
    if sys.platform!='win32':pytest.skip('Windows DPAPI')
    vault=Credentials(tmp_path);vault.save('local@example.invalid','test-secret')
    assert b'test-secret' not in vault.path.read_bytes()
    assert b'local@example.invalid' not in vault.path.read_bytes()
    assert vault.read()==Account().read()
    value=validate({'devices':[{'driver':'tapo-l530','address':'192.168.1.50',
                               'password':'test-secret'}]})
    assert 'password' not in value['devices'][0]
    vault.forget();assert not vault.configured


def test_native_tapo_binding_has_the_builder_api_used_by_adapter():
    import tapo
    from tapo.requests import LightSetDeviceInfoParams
    assert callable(tapo.ApiClient.l530) and callable(tapo.ColorLightHandler.set)
    for method in ('on','off','brightness','hue_saturation','color_temperature','send'):
        assert callable(getattr(LightSetDeviceInfoParams,method))


def test_tapo_defaults_adapt_to_acknowledgements_and_back_off_on_failure(monkeypatch):
    import ambientlink.tapo_driver as module
    clock=[100.]
    monkeypatch.setattr(module.time,'perf_counter',lambda:clock[0])
    async def run():
        device=Device();driver=adapter(device)
        assert driver.rate==10
        delay=[.03];fail=[False]
        class TimedRequest(Request):
            async def send(self,device):
                clock[0]+=delay[0]
                if fail[0]:raise TimeoutError('private SDK message')
                await super().send(device)
        device.set=TimedRequest
        await driver.connect();await driver.send((255,0,0),60)
        assert driver.rate==10  # fast replies are no longer artificially capped at 5
        delay[0]=.4
        for i in range(10):await driver.send((0,255,i*10),60)
        assert 1<=driver.rate<3 and 1/driver.rate>.4  # breathing room for a slow bulb
        before=driver.rate;fail[0]=True
        with pytest.raises(ValueError):await driver.send((0,0,255),60)
        assert driver.rate<before
        await driver.close(False);fail[0]=False;delay[0]=.02
        await driver.connect()
        throttled=driver.rate
        await driver.send((255,10,0),60)
        assert driver.rate<=throttled  # no immediate burst after a successful retry
        clock[0]+=10
        for i in range(25):await driver.send((255,i*5,0),60)
        assert driver.rate==10  # recovers automatically, without user tuning
    asyncio.run(run())


def test_shared_screen_defaults_preserve_explicit_calibration():
    defaults=validate({'devices':[{'driver':'tapo-l530','address':'192.168.1.50'}]})
    assert defaults['fps']==60 and defaults['smoothing']==350
    # Color transfer is model-dependent: don't force H600B calibration onto Tapo.
    customized=validate({**defaults,'smoothing':200,'devices':[{**defaults['devices'][0],'gains':[1,.8,.6],'gamma':True}]})
    assert customized['smoothing']==200 and customized['devices'][0]['gains']==[1,.8,.6]
    assert customized['devices'][0]['gamma'] is True
