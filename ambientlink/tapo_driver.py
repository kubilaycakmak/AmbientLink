"""Experimental L530/L530E local LAN adapter using the MIT tapo client."""
import asyncio
import colorsys
from .led_color import led_output


class TapoL530:
    rate=5  # Conservative request ceiling, NOT a measured hardware frame rate.
    transport='Tapo LAN acknowledged · experimental'

    def __init__(self,spec,credentials=None,client_factory=None):
        self.spec=spec;self.credentials=credentials;self.factory=client_factory
        self.client=None;self.device=None;self.original=None;self.last=None

    async def connect(self):
        if self.credentials is None:raise ValueError('Use Add Tapo to save your Tapo account first')
        credentials=self.credentials.read()
        if self.factory is None:
            from tapo import ApiClient
            factory=ApiClient
        else:factory=self.factory
        try:
            self.client=factory(credentials['username'],credentials['password'],timeout_s=3)
            device=await asyncio.wait_for(self.client.l530(self.spec['address']),10)
            info=await asyncio.wait_for(device.get_device_info(),5)
        except Exception:
            self.client=None;self.device=None
            raise ValueError('Tapo connection failed: check local IP, account, Wi-Fi and third-party compatibility setting') from None
        model=info.model.upper().split('(')[0].strip()
        if model not in ('L530','L530E'):
            self.client=None
            raise ValueError('This adapter is for Tapo L530/L530E only')
        if info.dynamic_light_effect_enable:
            self.client=None
            raise ValueError('Choose a solid color in the Tapo app first; dynamic effects are not restored')
        if self.original is None:
            self.original={k:getattr(info,k) for k in ('device_on','brightness','color_temp','hue','saturation')}
        self.device=device;self.last=None

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
            await asyncio.wait_for(request.send(self.device),3)
        except Exception:
            raise ValueError('Tapo did not acknowledge the light update; reconnecting') from None
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
        except Exception:
            raise ValueError('Tapo could not restore its previous light setting') from None
        finally:self.device=None;self.client=None;self.last=None
