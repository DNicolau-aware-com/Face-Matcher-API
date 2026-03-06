# -*- coding: utf-8 -*-
import requests
import pytest
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, IMAGES

PROBE_IMAGE_KEY     = 'dan_face'   # matches key in IMAGES dict in config.py
CANDIDATE_IMAGE_KEY = 'john_face'   # <-- update to a different image key before running
THRESHOLD           = 4.0

def test_verify_image_vs_image():
    # POST {{BASE_URL}}/facematch/compare
    url = f'{BASE_URL}/facematch/compare'

    probe_base64     = IMAGES.get(PROBE_IMAGE_KEY)
    candidate_base64 = IMAGES.get(CANDIDATE_IMAGE_KEY)

    if not probe_base64:
        print(f'[VERIFY] ERROR: Probe image key "{PROBE_IMAGE_KEY}" not found in config. Check your .env file.')
        pytest.fail(f'[SKIP] Probe image key "{PROBE_IMAGE_KEY}" not found in config. Check your .env file.')
    if not candidate_base64:
        print(f'[VERIFY] ERROR: Candidate image key "{CANDIDATE_IMAGE_KEY}" not found in config. Check your .env file.')
        pytest.fail(f'[SKIP] Candidate image key "{CANDIDATE_IMAGE_KEY}" not found in config. Check your .env file.')

    payload = {
        'probe':     {'image': probe_base64},
        'candidate': {'image': candidate_base64},
        'threshold': THRESHOLD,
    }

    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[VERIFY] URL          : {url}')
    print(f'[VERIFY] Mode         : image vs image')
    print(f'[VERIFY] Threshold    : {THRESHOLD}')
    print(f'[VERIFY] Status       : {r.status_code}')
    print(f'[VERIFY] Trace ID     : {r.headers.get("x-aware-trace-id", "not returned")}')

    if r.status_code == 200:
        body = r.json()
        print(f'[VERIFY] Score        : {body.get("score")}')
        print(f'[VERIFY] Match        : {body.get("match")}')
    else:
        print(f'[VERIFY] Response     : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

def test_verify_same_image_vs_same_image():
    # POST {{BASE_URL}}/facematch/compare — same image as both probe and candidate (expect match)
    url       = f'{BASE_URL}/facematch/compare'
    image_key = 'dan_face'

    image_base64 = IMAGES.get(image_key)
    if not image_base64:
        print(f'[VERIFY SAME] ERROR: Image key "{image_key}" not found in config. Check your .env file.')
        pytest.fail(f'[SKIP] Image key "{image_key}" not found in config. Check your .env file.')

    payload = {
        'probe':     {'image': image_base64},
        'candidate': {'image': image_base64},
        'threshold': THRESHOLD,
    }

    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[VERIFY SAME] URL       : {url}')
    print(f'[VERIFY SAME] Mode      : same image vs same image')
    print(f'[VERIFY SAME] Image key : {image_key}')
    print(f'[VERIFY SAME] Threshold : {THRESHOLD}')
    print(f'[VERIFY SAME] Status    : {r.status_code}')
    print(f'[VERIFY SAME] Trace ID  : {r.headers.get("x-aware-trace-id", "not returned")}')

    if r.status_code == 200:
        body = r.json()
        print(f'[VERIFY SAME] Score     : {body.get("score")}')
        print(f'[VERIFY SAME] Match     : {body.get("match")}')
    else:
        print(f'[VERIFY SAME] Response  : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

if __name__ == '__main__':
    test_verify_image_vs_image()
    test_verify_same_image_vs_same_image()
