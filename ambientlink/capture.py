"""Downsample the Windows primary display in GDI before copying pixels to Python."""
import ctypes
from ctypes import wintypes

from PIL import Image, ImageStat


class BitmapHeader(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("width", wintypes.LONG),
                ("height", wintypes.LONG), ("planes", wintypes.WORD),
                ("bits", wintypes.WORD), ("compression", wintypes.DWORD),
                ("imageSize", wintypes.DWORD), ("xppm", wintypes.LONG),
                ("yppm", wintypes.LONG), ("used", wintypes.DWORD),
                ("important", wintypes.DWORD)]


class GdiCapture:
    width, height = 96, 54

    def __enter__(self):
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.gdi = ctypes.WinDLL("gdi32", use_last_error=True)
        handle = wintypes.HANDLE
        self.user.GetDC.argtypes = [wintypes.HWND]; self.user.GetDC.restype = handle
        self.user.ReleaseDC.argtypes = [wintypes.HWND, handle]
        self.user.SetThreadDpiAwarenessContext.argtypes = [handle]
        self.user.SetThreadDpiAwarenessContext.restype = handle
        self.gdi.CreateCompatibleDC.argtypes = [handle]; self.gdi.CreateCompatibleDC.restype = handle
        self.gdi.CreateDIBSection.argtypes = [handle, ctypes.POINTER(BitmapHeader), wintypes.UINT, ctypes.POINTER(ctypes.c_void_p), handle, wintypes.DWORD]
        self.gdi.CreateDIBSection.restype = handle
        self.gdi.SelectObject.argtypes = [handle, handle]; self.gdi.SelectObject.restype = handle
        self.gdi.DeleteObject.argtypes = [handle]; self.gdi.DeleteDC.argtypes = [handle]
        self.gdi.SetStretchBltMode.argtypes = [handle, ctypes.c_int]
        self.gdi.SetBrushOrgEx.argtypes = [handle, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
        self.gdi.StretchBlt.argtypes = [handle, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                      handle, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
        self.screen = self.memory = self.bitmap = self.old = None
        self.dpi = self.user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        try:
            self.screen = self.user.GetDC(None)
            self.memory = self.gdi.CreateCompatibleDC(self.screen)
            header = BitmapHeader(ctypes.sizeof(BitmapHeader), self.width, -self.height, 1, 32, 0, 0, 0, 0, 0, 0)
            self.pixels = ctypes.c_void_p()
            self.bitmap = self.gdi.CreateDIBSection(self.screen, ctypes.byref(header), 0, ctypes.byref(self.pixels), None, 0)
            if not all((self.screen, self.memory, self.bitmap, self.pixels.value)):
                raise OSError("Could not initialize primary-screen capture")
            self.old = self.gdi.SelectObject(self.memory, self.bitmap)
            self.gdi.SetStretchBltMode(self.memory, 4)  # HALFTONE: average while shrinking.
            self.gdi.SetBrushOrgEx(self.memory, 0, 0, None)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def color(self):
        width, height = self.user.GetSystemMetrics(0), self.user.GetSystemMetrics(1)
        if width <= 0 or height <= 0 or not self.gdi.StretchBlt(
            self.memory, 0, 0, self.width, self.height,
            self.screen, 0, 0, width, height, 0x40CC0020,  # SRCCOPY | CAPTUREBLT
        ):
            raise OSError("Primary screen is unavailable")
        self.gdi.GdiFlush()
        small = ctypes.string_at(self.pixels, self.width * self.height * 4)
        sample = Image.frombytes("RGB", (self.width, self.height), small, "raw", "BGRX")
        return tuple(round(v) for v in ImageStat.Stat(sample).mean)

    def __exit__(self, *_):
        if self.old and self.memory: self.gdi.SelectObject(self.memory, self.old)
        if self.bitmap: self.gdi.DeleteObject(self.bitmap)
        if self.memory: self.gdi.DeleteDC(self.memory)
        if self.screen: self.user.ReleaseDC(None, self.screen)
        if self.dpi: self.user.SetThreadDpiAwarenessContext(self.dpi)


class PrimaryCapture:
    """DXGI capture on the actual primary output; no screenshot is persisted."""
    def __enter__(self):
        import re
        import sys
        # comtypes otherwise selects STA when DXcam is first imported. This
        # asyncio thread has no GUI message pump: STA strands WinRT BLE replies.
        sys.coinit_flags = 0  # COINIT_MULTITHREADED, also for standalone callers.
        import comtypes
        comtypes.CoInitializeEx(0)
        self.com = comtypes
        self.camera = None
        self.timer_active = False
        try:
            import dxcam
            matches = re.findall(r'Device\[(\d+)\] Output\[(\d+)\]:[^\n]*Primary:True', dxcam.output_info())
            if len(matches) != 1:
                raise OSError("Could not identify the Windows primary monitor")
            device, output = map(int, matches[0])
            self.camera = dxcam.create(device_idx=device, output_idx=output,
                                       output_color="BGRA", processor_backend="numpy", max_buffer_len=2)
            self.timer = ctypes.WinDLL("winmm")
            self.timer_active = self.timer.timeBeginPeriod(1) == 0
            return self
        except BaseException:
            self.__exit__(None,None,None)
            raise

    def colors(self, mode="zones"):
        from .colors import screen_colors
        frame = self.camera.grab(new_frame_only=False, copy=False)
        if frame is None:
            raise OSError("Primary screen is unavailable")
        # Area filtering includes thin text and its background instead of picking
        # individual colored subpixels. Convert BGR only after shrinking.
        import numpy as np
        height,width = frame.shape[:2]
        # Ignore DXGI's unused alpha byte. RGBA resizing needlessly performs
        # alpha premultiplication across millions of pixels every frame.
        image = Image.frombuffer('RGBX',(width,height),frame,'raw','RGBX',0,1)
        small = image.reduce((max(1,width//160),max(1,height//90)))
        return screen_colors(np.asarray(small)[... ,2::-1], mode)

    def color(self):
        return self.colors("dominant")[1]

    def __exit__(self, *_):
        try:
            if self.camera: self.camera.release()
        finally:
            if self.timer_active: self.timer.timeEndPeriod(1)
            self.com.CoUninitialize()
