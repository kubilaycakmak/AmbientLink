import json
import math
import re
from .drivers import REGISTRY,private_ipv4

DEFAULT={'devices':[],'mode':'dominant','brightness':60,'fps':60,'smoothing':280,'rgb':[255,170,60]}


def validate(value):
    if not isinstance(value,dict) or set(value)-set(DEFAULT):raise ValueError('Invalid settings')
    out={**DEFAULT,**value}
    for key,low,high in [('brightness',0,100),('fps',5,60),('smoothing',50,700)]:
        if type(out[key]) is not int or not low<=out[key]<=high:raise ValueError('Invalid '+key)
    if out['mode'] not in ('dominant','zones','average'):raise ValueError('Invalid screen mode')
    if not isinstance(out['rgb'],list) or len(out['rgb'])!=3 or any(type(v) is not int or not 0<=v<=255 for v in out['rgb']):raise ValueError('Invalid RGB')
    if not isinstance(out['devices'],list) or len(out['devices'])>24:raise ValueError('Select at most 24 devices')
    devices=[];seen=set()
    for item in out['devices']:
        if not isinstance(item,dict) or item.get('driver') not in REGISTRY:raise ValueError('Unsupported driver')
        driver=item['driver'];address=item.get('address','')
        if driver=='govee-h600b':
            if not isinstance(address,str) or not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}',address):raise ValueError('Invalid Bluetooth address')
            address=address.upper()
        else:address=private_ipv4(address)
        if (driver,address) in seen:raise ValueError('Device already selected')
        seen.add((driver,address))
        zone=item.get('zone',1);gamma=item.get('gamma',driver=='govee-h600b');enabled=item.get('enabled',True)
        gains=item.get('gains',[1,1,1])
        if type(zone)is not int or zone not in (0,1,2) or type(gamma)is not bool or type(enabled)is not bool:raise ValueError('Invalid device options')
        if not isinstance(gains,list) or len(gains)!=3 or any(type(v)not in (int,float) or not math.isfinite(v) or not .1<=v<=2 for v in gains):raise ValueError('RGB gains must be between 0.1 and 2')
        devices.append({'driver':driver,'address':address,'name':str(item.get('name',driver))[:64],'zone':zone,'gamma':gamma,'enabled':enabled,'gains':gains})
    return {**out,'devices':devices}


def load(path):return validate(json.loads(path.read_text())) if path.exists() else validate({})
def save(path,value):
    value=validate(value);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2));temp.replace(path)
    return value
