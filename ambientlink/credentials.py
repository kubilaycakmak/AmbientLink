"""Current-Windows-user DPAPI storage; secrets never enter settings or state."""
import ctypes
from ctypes import wintypes
import json


class Blob(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]


def protect(data, decrypt=False):
    crypt=ctypes.WinDLL('crypt32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    buffer=ctypes.create_string_buffer(data)
    source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)))
    result=Blob()
    fn=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,
                 ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    fn.restype=wintypes.BOOL
    kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
    if not fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(result)):
        raise ValueError('Cannot access Tapo credentials for this Windows account; save them again')
    try:return ctypes.string_at(result.data,result.size)
    finally:kernel.LocalFree(result.data)


class Credentials:
    def __init__(self,root):self.path=root/'tapo-credentials.dpapi'
    @property
    def configured(self):return self.path.is_file()
    def read(self):
        if not self.configured:raise ValueError('Use Add Tapo to save your Tapo account first')
        try:return json.loads(protect(self.path.read_bytes(),decrypt=True))
        except Exception:raise ValueError('Cannot unlock Tapo account; save it again on this Windows account') from None
    def save(self,username,password):
        if not isinstance(username,str) or not isinstance(password,str) or not username.strip() or not password or len(username)>320 or len(password)>1024:
            raise ValueError('Enter your Tapo email and password')
        encrypted=protect(json.dumps({'username':username.strip(),'password':password}).encode())
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix('.new');temp.write_bytes(encrypted);temp.replace(self.path)
    def forget(self):self.path.unlink(missing_ok=True)
