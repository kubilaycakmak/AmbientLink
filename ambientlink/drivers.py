"""Small local-device adapter interface. No account or cloud credentials."""
import asyncio
import ipaddress
import json
import socket
import time
from .govee_ble import Bulb
from .led_color import led_output


def private_ipv4(value):
    address=ipaddress.ip_address(value)
    if address.version!=4 or not address.is_private or address.is_loopback or address.is_multicast or address.is_unspecified:
        raise ValueError('Enter a private LAN IPv4 address')
    return str(address)


class H600B:
    rate=30
    def __init__(self, spec):
        self.spec=spec; self.bulb=Bulb(spec['address']); self.original=None; self.last=None

    async def connect(self):
        await self.bulb.connect()
        state=await self.bulb.status()
        if state.get('rgb') is None:
            raise ValueError('Set the bulb to a solid RGB color in Govee Home once, then close that app')
        if self.original is None: self.original=state
        self.bulb.streaming(True)
        self.last=None

    async def send(self, rgb, brightness):
        if not self.bulb.connected: await self.connect()
        color,dim=led_output(rgb,brightness,self.spec.get('gamma',False))
        value=(color,dim,max(color)>0 and dim>0)
        if self.last==value: return False
        if not self.last or self.last[0]!=color: await self.bulb.color(color)
        if not self.last or self.last[1]!=dim: await self.bulb.brightness(dim)
        if not self.last or self.last[2]!=value[2]: await self.bulb.power(value[2])
        self.last=value
        return True

    async def close(self, restore=True):
        try:
            if restore and self.original and self.bulb.connected:
                await self.bulb.color(self.original['rgb'])
                await self.bulb.brightness(self.original['brightness'])
                await self.bulb.power(self.original['power'])
        finally: await self.bulb.close()


class GoveeLAN:
    # Conservative default; LAN devices do not acknowledge color commands.
    rate=10
    def __init__(self,spec):
        self.spec=spec;self.address=private_ipv4(spec['address']);self.sock=None;self.last=None

    async def connect(self):
        if self.sock: self.sock.close()
        self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.sock.setblocking(False);self.last=None

    async def command(self,cmd,data):
        packet=json.dumps({'msg':{'cmd':cmd,'data':data}},separators=(',',':')).encode()
        await asyncio.get_running_loop().sock_sendto(self.sock,packet,(self.address,4003))

    async def send(self,rgb,brightness):
        if not self.sock: await self.connect()
        color,dim=led_output(rgb,brightness,self.spec.get('gamma',False))
        value=(color,dim,max(color)>0 and dim>0)
        if self.last==value:return False
        if not value[2]: await self.command('turn',{'value':0})
        else:
            if not self.last or self.last[0]!=color:
                await self.command('colorwc',{'color':dict(zip(('r','g','b'),color)),'colorTemInKelvin':0})
            if not self.last or self.last[1]!=dim:await self.command('brightness',{'value':dim})
            if not self.last or not self.last[2]:await self.command('turn',{'value':1})
        self.last=value
        return True

    async def close(self,restore=True):
        # No trustworthy original-state snapshot: stop sends no speculative restore.
        if self.sock:self.sock.close();self.sock=None


REGISTRY={'govee-h600b':H600B,'govee-lan':GoveeLAN}


def lan_discover():
    found={}
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.bind(('',4002))
        sock.settimeout(.4)
        sock.setsockopt(socket.IPPROTO_IP,socket.IP_MULTICAST_TTL,1)
        message=b'{"msg":{"cmd":"scan","data":{"account_topic":"reserve"}}}'
        # Send on each local IPv4 interface; a direct cable must not hide Wi-Fi.
        addresses={item[4][0] for item in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET)}
        for address in addresses:
            try:
                sock.setsockopt(socket.IPPROTO_IP,socket.IP_MULTICAST_IF,socket.inet_aton(address))
                sock.sendto(message,('239.255.255.250',4001))
            except OSError:pass
        deadline=time.monotonic()+4
        while time.monotonic()<deadline:
            try:
                packet,peer=sock.recvfrom(8192)
                data=json.loads(packet)['msg']
                if data['cmd']!='scan':continue
                address=private_ipv4(peer[0])
                model=str(data['data'].get('sku','Govee LAN'))[:40]
                found[address]={'driver':'govee-lan','address':address,'name':model,'model':model}
            except (OSError,ValueError,KeyError,TypeError):continue
    return list(found.values())


async def discover():
    from bleak import BleakScanner
    errors=[];results=[]
    async def ble():
        try:
            devices=await BleakScanner.discover(timeout=5,return_adv=True)
            return [{'driver':'govee-h600b','address':device.address,'name':advert.local_name or device.name,'model':'H600B'}
                    for device,advert in devices.values() if 'H600B' in (advert.local_name or device.name or '').upper()]
        except Exception as error:
            errors.append('Bluetooth: '+str(error));return []
    async def lan():
        try:return await asyncio.to_thread(lan_discover)
        except OSError as error:
            errors.append('LAN discovery: '+str(error));return []
    for batch in await asyncio.gather(ble(),lan()):results.extend(batch)
    return {'devices':results,'errors':errors}
