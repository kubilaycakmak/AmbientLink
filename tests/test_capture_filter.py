import numpy as np
from ambientlink.capture import PrimaryCapture


def sampled(frame):
    class Camera:
        def grab(self,**kwargs):return frame
    capture=PrimaryCapture();capture.camera=Camera()
    return capture.colors('dominant')[0]


def test_area_filter_includes_thin_text_and_ignores_alpha():
    frame=np.zeros((900,1600,4),dtype=np.uint8)
    frame[::10,:,:3]=255
    # Point sampling at every tenth row would return white, not ten percent.
    result=sampled(frame)
    assert len(set(result))==1 and 25<=result[0]<=26


def test_capture_bgr_order_and_subpixel_neutrality():
    frame=np.zeros((900,1600,4),dtype=np.uint8)
    frame[:,:,:3]=(10,60,180)
    assert sampled(frame)==(180,60,10)
    frame=np.zeros((1080,1920,4),dtype=np.uint8)
    for i in range(3):frame[:,i::3,i]=255
    assert sampled(frame)==(85,85,85)
