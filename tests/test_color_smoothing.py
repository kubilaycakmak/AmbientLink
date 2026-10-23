import pytest

from ambientlink.color_smoothing import LinearLightSmoother, drive, encode
from ambientlink.led_color import led_output


def emitted(rgb):
    rgb=tuple(round(v) for v in rgb)
    output,dim=led_output(rgb,100,True)
    return tuple(c*dim/100 for c in output)


def luminance(rgb):
    return sum(c*w for c,w in zip(rgb,(.2126,.7152,.0722)))


@pytest.mark.parametrize('rgb', [(128,101,56),(255,0,0),(0,0,0),(30,80,120),(9,12,8),(255,255,255)])
def test_transfer_roundtrip_preserves_verified_colors(rgb):
    assert tuple(round(v) for v in encode(drive(rgb))) == rgb


@pytest.mark.parametrize('start,target',[
    ((255,0,0),(0,0,255)), ((128,101,56),(30,80,120)),
    ((30,80,120),(128,101,56)), ((50,50,50),(0,0,255)),
    ((0,0,255),(50,50,50)),
])
@pytest.mark.parametrize('fps',[30,60])
def test_hue_crossfades_do_not_manufacture_a_light_peak(start,target,fps):
    smoother=LinearLightSmoother()
    smoother.update([start],1/fps)
    bound=max(luminance(drive(start)),luminance(drive(target)))
    for _ in range(8*fps):
        result=smoother.update([target],1/fps)[0]
        assert luminance(smoother.channels[0]) <= bound+1e-8
        # Hardware dimmer is integer percent; allow its final rounding only.
        assert luminance(emitted(result)) <= bound+2
    assert tuple(round(v) for v in result)==target


@pytest.mark.parametrize('fps',[30,60])
def test_fast_black_neutral_brightness_and_first_frame_response(fps):
    s=LinearLightSmoother()
    s.update([(255,255,255),(255,0,0)],1/fps)
    first=s.update([(0,0,0),(0,0,255)],1/fps)
    assert first[1][2]>0  # no frame queue or delayed start
    for _ in range(round(.25*fps)-1):
        result=s.update([(0,0,0),(0,0,255)],1/fps)
    assert result[0]==(0,0,0)
    assert 0<result[1][2]<255
    s=LinearLightSmoother();s.update([(25,25,25)],1/fps)
    previous=25
    for _ in range(fps//2):
        value=s.update([(255,255,255)],1/fps)[0]
        assert 0<=max(value)-previous<=230/(.45*fps)+1e-6
        previous=max(value)
    assert max(value)==pytest.approx(255)
    s=LinearLightSmoother();s.update([(200,200,200)],1/fps)
    for _ in range(fps//2):
        value=s.update([(20,20,20)],1/fps)[0]
    assert max(value)==pytest.approx(20)


def test_zero_elapsed_and_capture_stall_cannot_jump_to_target():
    s=LinearLightSmoother();s.update([(0,0,0)],1/60)
    assert s.update([(255,255,255)],0)==[(0,0,0)]
    assert max(s.update([(255,255,255)],2)[0])<=60


@pytest.mark.parametrize('fps',[15,30,60])
@pytest.mark.parametrize('desktop',[(35,35,35),(180,180,180)])
def test_movie_exit_retargets_latest_scene_without_seconds_of_old_color_tail(fps,desktop):
    s=LinearLightSmoother()
    for rgb in [(128,101,56),(30,80,120),(180,30,50),(50,100,20)]:
        for _ in range(fps//8):s.update([rgb],1/fps)
    previous=s.channels[0]
    target=drive(desktop)
    for _ in range(round(.5*fps)):
        value=s.update([desktop],1/fps)[0]
        current=s.channels[0]
        # Once on the desktop, each channel moves only toward the desktop,
        # never back through earlier movie colors.
        assert all(min(a,b)-1e-8<=c<=max(a,b)+1e-8 for a,b,c in zip(previous,target,current))
        previous=current
    assert tuple(round(v) for v in value)==desktop


def test_small_source_noise_does_not_keep_restarting_transition():
    s=LinearLightSmoother();s.update([(128,101,56)],1/60)
    for n in range(36):
        target=(35+n%2,)*3
        value=s.update([target],1/60)[0]
    assert max(abs(a-b) for a,b in zip(value,target))<.01


def test_uncorrected_devices_use_raw_rgb_without_an_extra_gamma_transform():
    s=LinearLightSmoother(corrected=False)
    assert s.update([(128,101,56)],1/60)==[(128,101,56)]
    previous=(128,101,56)
    for _ in range(30):
        value=s.update([(30,80,120)],1/60)[0]
        assert all(min(a,b)<=c<=max(a,b) for a,b,c in zip(previous,(30,80,120),value))
        previous=value
    assert tuple(round(v) for v in value)==(30,80,120)
