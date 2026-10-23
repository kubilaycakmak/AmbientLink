import numpy as np
from ambientlink.colors import screen_colors, dominant


def test_sparse_white_text_does_not_light_dark_zone():
    frame=np.zeros((100,300,3),dtype=np.uint8)
    frame[:10,:100]=255
    frame[:,100:200]=(255,0,0)
    frame[:,200:]=(0,255,0)
    left,center,right=screen_colors(frame)
    assert left==(26,26,26)
    assert center==(255,0,0) and right==(0,255,0)


def test_title_card_is_not_cropped_into_full_brightness():
    frame=np.zeros((100,100,3),dtype=np.uint8)
    frame[45:55]=255
    assert screen_colors(frame,'dominant')==[(26,26,26)]*3


def test_letterbox_crop_preserves_lit_content_but_not_black_sides():
    frame=np.zeros((100,300,3),dtype=np.uint8)
    frame[15:85,100:]=(180,80,20)
    assert screen_colors(frame)==[(0,0,0),(180,80,20),(180,80,20)]


def test_neutral_fringe_is_neutral_but_pale_blue_remains_blue():
    assert dominant(np.full((10,10,3),(245,249,255)))==(255,255,255)
    assert dominant(np.full((10,10,3),(180,210,255)))==(180,210,255)
