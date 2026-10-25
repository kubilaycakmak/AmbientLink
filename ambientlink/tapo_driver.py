"""Experimental L530/L530E local LAN adapter using the MIT tapo client."""
import asyncio
import colorsys
import re
import time
from .led_color import led_output
from .diagnostics import DeviceError


def tapo_error(error, stage=None, discovery=None, code='tapo_connect'):
    # tapo's Rust binding wraps every error in a generic Python Exception.
    # Recognize fixed SDK markers locally; never retain/export its raw text,
    # which can contain URLs, credentials or device identifiers.
    raw=str(error)
    category=None;retry_after=5
    message='Tapo connection failed. Check bulb IP, local network and account; download diagnostics for details.'
    if 'TPAP_AUTH_ATTEMPTS_LIMIT' in raw:
        code='tapo_locked';category='permission';retry_after=None
        message='Tapo locked logins after failed attempts. Retries paused. Stop, check the account, wait for the lock to expire, then restart.'
    elif any(marker in raw for marker in ('HASH_MISMATCH','TPAP_CREDENTIALS')):
        code='tapo_auth';category='permission';retry_after=None
        message='Tapo rejected the account. Retries paused. Stop, save the exact Tapo email/password (case-sensitive), then restart.'
    elif 'FORBIDDEN' in raw or re.search(r'status_code:\s*403\b',raw):
        code='tapo_forbidden';category='permission';retry_after=None
        message='Tapo denied local access (403). Retries paused. Check Third-Party Compatibility in Tapo, then stop and restart control.'
    elif 'UnsupportedProtocol' in raw:
        code='tapo_protocol';category='invalid_input';retry_after=None
        message='This Tapo firmware login protocol is unsupported. Retries paused. Download diagnostics and report the bulb firmware version.'
    elif isinstance(error,TimeoutError) or (raw.startswith('Http(') and any(marker in raw.lower() for marker in ('timedout','timed out','timeout'))):
        code='tapo_timeout';category='timeout'
        message='Tapo local connection timed out. Check the current bulb IP, PC LAN access and VPN/guest-network isolation. Retrying.'
    elif isinstance(error,OSError) or raw.startswith('Http('):
        code='tapo_network';category='network'
        message='Tapo local network request failed. Check bulb IP and PC LAN access; allow local traffic through VPN/firewall. Retrying.'
    if stage=='device_info' and code=='tapo_timeout':
        message='Tapo login succeeded, but reading bulb settings timed out. Retrying; download diagnostics if this repeats.'
    if stage is None and code=='tapo_update':
        message='Tapo did not acknowledge the light update; reconnecting'
    return DeviceError(message,code,error,category=category,stage=stage,discovery=discovery,retry_after=retry_after)


class TapoL530:
    max_rate=10  # Upper bound, not a promise of physical bulb FPS.
    rate=10
    transport='Tapo LAN acknowledged · experimental'

    def __init__(self,spec,credentials=None,client_factory=None):
        self.spec=spec;self.credentials=credentials;self.factory=client_factory
        self.client=None;self.device=None;self.original=None;self.last=None
        self.response_seconds=None
        self.rate_hold_until=0.

    def observe_response(self,seconds):
        # Keep one acknowledged command in flight and leave 15% headroom on
        # slower bulbs. Never queue intermediate colors to chase the ceiling.
        self.response_seconds=seconds if self.response_seconds is None else .7*self.response_seconds+.3*seconds
        capacity=min(self.max_rate,1/max(.001,self.response_seconds*1.15))
        ceiling=self.rate if time.perf_counter()<self.rate_hold_until else self.rate*1.25
        self.rate=max(1,min(capacity,ceiling))

    async def connect(self):
        if self.credentials is None:raise DeviceError('Use Add Tapo to save your Tapo account first','tapo_account')
        if self.factory is None:
            from tapo import ApiClient
            factory=ApiClient
        else:factory=self.factory
        stage='credentials';discovery='unavailable'
        try:
            credentials=self.credentials.read()
            # A few firmwares only enable local HTTP after a discovery query.
            # Unicast to the configured bulb only, without account credentials.
            # No UDP reply must not block an otherwise working HTTP connection.
            discovery=await self.wake_local_api(factory)
            stage='login'
            self.client=factory(credentials['username'],credentials['password'],timeout_s=10)
            device=await asyncio.wait_for(self.client.l530(self.spec['address']),30)
            stage='device_info'
            info=await asyncio.wait_for(device.get_device_info(),10)
        except Exception as error:
            self.client=None;self.device=None
            if stage=='credentials':
                raise DeviceError('Tapo account could not be read. Stop, save it again with Add Tapo, then restart.',
                                  'tapo_account',error,stage=stage,retry_after=None) from None
            raise tapo_error(error,stage,discovery) from None
        model=info.model.upper().split('(')[0].strip()
        if model not in ('L530','L530E'):
            self.client=None
            raise DeviceError('This adapter is for Tapo L530/L530E only','tapo_model')
        if info.dynamic_light_effect_enable:
            self.client=None
            raise DeviceError('Choose a solid color in the Tapo app first; dynamic effects are not restored','tapo_effect')
        if self.original is None:
            self.original={k:getattr(info,k) for k in ('device_on','brightness','color_temp','hue','saturation')}
        self.device=device;self.last=None

    async def wake_local_api(self,factory):
        if not hasattr(factory,'discover_devices_raw'):return 'unavailable'
        async def probe():
            stream=await factory.discover_devices_raw(self.spec['address'],timeout_s=2)
            async for candidate in stream:
                if candidate.get().ip==self.spec['address']:return 'replied'
            return 'no_reply'
        try:return await asyncio.wait_for(probe(),2.5)
        except TimeoutError:return 'no_reply'
        except Exception:return 'unavailable'

    async def send(self,rgb,brightness):
        if self.device is None:await self.connect()
        color,dim=led_output(rgb,brightness,self.spec.get('gamma',False))
        hue,saturation,level=colorsys.rgb_to_hsv(*(c/255 for c in color))
        on=level>0 and dim>0
        dim=max(1,min(100,round(dim*level)))
        hue=round(hue*360)%360;saturation=round(saturation*100)
        value=(on,hue,saturation,dim) if on else (False,)
        if value==self.last:return False
        try:
            request=self.device.set()
            if not on:request=request.off()
            else:
                # The library's HSV builder accepts saturation 1..100. Use the
                # device white channel for neutral input (D65 reference).
                request=(request.color_temperature(6500) if saturation==0 else request.hue_saturation(hue,saturation))
                request=request.brightness(dim).on()
            started=time.perf_counter()
            await asyncio.wait_for(request.send(self.device),3)
            self.observe_response(time.perf_counter()-started)
        except Exception as error:
            self.rate=max(1,self.rate/2)
            self.rate_hold_until=time.perf_counter()+10
            raise tapo_error(error,code='tapo_update') from None
        self.last=value
        return True

    async def close(self,restore=True):
        try:
            if restore and self.original and self.device:
                state=self.original;request=self.device.set()
                if state['color_temp']:
                    request=request.color_temperature(state['color_temp'])
                elif state['saturation']:
                    request=request.hue_saturation(state['hue'] or 0,state['saturation'])
                else:request=request.color_temperature(6500)
                request=request.brightness(max(1,state['brightness']))
                request=request.on() if state['device_on'] else request.off()
                await asyncio.wait_for(request.send(self.device),3)
        except Exception as error:
            raise DeviceError('Tapo could not restore its previous light setting','tapo_restore',error) from None
        finally:self.device=None;self.client=None;self.last=None
