# -*- coding: utf-8 -*-
# Tests POST /facematch/upload/compare in image-vs-image mode:
# both probe and candidate are uploaded as files — no gallery or enrolled identity needed.
# This is the multipart equivalent of POST /facematch/compare with two base64 image payloads.
import requests
import pytest
import base64
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, IMAGES

PROBE_KEY         = 'dan_face'
CANDIDATE_KEY     = 'dan_face'   # same image → expect match=true
DIFFERENT_KEY     = 'jane_face'
THRESHOLD         = 4.0
THRESHOLD_NO_MATCH = 999.0       # deliberately above any real score to force match=false

UPLOAD_HEADERS = {k: v for k, v in HEADERS.items() if k.lower() != 'content-type'}


def test_upload_compare_same_image_vs_same_image():
    """Uploading the same image as both probe and candidate should return match=true."""
    image_base64 = IMAGES.get(PROBE_KEY)
    if not image_base64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config. Check your .env file.')

    image_bytes = base64.b64decode(image_base64)

    url = f'{BASE_URL}/facematch/upload/compare'

    r = requests.post(
        url,
        headers=UPLOAD_HEADERS,
        files={
            'probe_image':     ('probe.jpg',     image_bytes, 'image/jpeg'),
            'candidate_image': ('candidate.jpg', image_bytes, 'image/jpeg'),
        },
        data={'threshold': THRESHOLD},
    )

    print(f'[UPLOAD COMPARE IMG] URL       : {url}')
    print(f'[UPLOAD COMPARE IMG] Mode      : image vs image (same)')
    print(f'[UPLOAD COMPARE IMG] Status    : {r.status_code}')
    print(f'[UPLOAD COMPARE IMG] Trace ID  : {r.headers.get("x-aware-trace-id", "not returned")}')

    if r.status_code == 200:
        body = r.json()
        print(f'[UPLOAD COMPARE IMG] Score     : {body.get("score")}')
        print(f'[UPLOAD COMPARE IMG] Match     : {body.get("match")}')
        assert body.get('match') is True, f'Expected match=true for same image, got: {body}'
    else:
        print(f'[UPLOAD COMPARE IMG] Response  : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'


def test_upload_compare_different_images():
    """Uploading two different identities should return match=false."""
    probe_base64     = IMAGES.get(PROBE_KEY)
    candidate_base64 = IMAGES.get(DIFFERENT_KEY)

    if not probe_base64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config. Check your .env file.')
    if not candidate_base64:
        pytest.fail(f'Image key "{DIFFERENT_KEY}" not found in config. Check your .env file.')

    probe_bytes     = base64.b64decode(probe_base64)
    candidate_bytes = base64.b64decode(candidate_base64)

    url = f'{BASE_URL}/facematch/upload/compare'

    r = requests.post(
        url,
        headers=UPLOAD_HEADERS,
        files={
            'probe_image':     ('probe.jpg',     probe_bytes,     'image/jpeg'),
            'candidate_image': ('candidate.jpg', candidate_bytes, 'image/jpeg'),
        },
        data={'threshold': THRESHOLD_NO_MATCH},
    )

    print(f'[UPLOAD COMPARE IMG] URL       : {url}')
    print(f'[UPLOAD COMPARE IMG] Mode      : image vs image (different)')
    print(f'[UPLOAD COMPARE IMG] Threshold : {THRESHOLD_NO_MATCH} (forces match=false)')
    print(f'[UPLOAD COMPARE IMG] Status    : {r.status_code}')
    print(f'[UPLOAD COMPARE IMG] Trace ID  : {r.headers.get("x-aware-trace-id", "not returned")}')

    if r.status_code == 200:
        body = r.json()
        print(f'[UPLOAD COMPARE IMG] Score     : {body.get("score")}')
        print(f'[UPLOAD COMPARE IMG] Match     : {body.get("match")}')
        assert body.get('match') is False, f'Expected match=false with threshold {THRESHOLD_NO_MATCH}, got: {body}'
    else:
        print(f'[UPLOAD COMPARE IMG] Response  : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'


if __name__ == '__main__':
    test_upload_compare_same_image_vs_same_image()
    test_upload_compare_different_images()
