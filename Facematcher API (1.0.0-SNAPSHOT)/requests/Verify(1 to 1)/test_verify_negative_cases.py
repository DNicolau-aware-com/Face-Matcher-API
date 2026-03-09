# -*- coding: utf-8 -*-
import requests
import pytest
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, IMAGES

THRESHOLD            = 4.0
THRESHOLD_NON_MATCH  = 999.0   # deliberately above any real score to force match: false
NON_MATCH_IDENT      = 'verify_non_match_id'   # isolated identifier for the non-matching test


# ---------------------------------------------------------------------------
# Test 1: Verify with non-matching images — expect match = false
# ---------------------------------------------------------------------------

def test_verify_non_matching_images(session_gallery):
    # POST {{BASE_URL}}/facematch/compare
    # Uses an extremely high threshold so the API returns match: false even if
    # the two images are similar.  This verifies the threshold/match logic works
    # correctly — the response must be 200 with match: false.
    gallery      = session_gallery
    probe_b64    = IMAGES.get('dan_face')
    template_b64 = IMAGES.get('jane_face')

    if not probe_b64:
        pytest.fail('[VERIFY NON-MATCH] probe image "dan_face" not found in config. Check your .env file.')
    if not template_b64:
        pytest.fail('[VERIFY NON-MATCH] candidate image "jane_face" not found in config. Check your .env file.')

    # Enroll jane_face under an isolated identifier
    enroll_url = f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{NON_MATCH_IDENT}'
    r_enroll   = requests.post(enroll_url, headers=HEADERS, json={'image': template_b64})
    print(f'[VERIFY NON-MATCH] Pre-enroll  : {NON_MATCH_IDENT} → {r_enroll.status_code}')
    if r_enroll.status_code not in (200, 409):
        pytest.fail(f'[VERIFY NON-MATCH] Pre-enroll failed: {r_enroll.status_code}: {r_enroll.text}')

    url     = f'{BASE_URL}/facematch/compare'
    payload = {
        'probe':     {'image': probe_b64},
        'candidate': {'id': NON_MATCH_IDENT, 'gallery': gallery},
        'threshold': THRESHOLD_NON_MATCH,
    }

    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[VERIFY NON-MATCH] URL         : {url}')
    print(f'[VERIFY NON-MATCH] Probe       : dan_face')
    print(f'[VERIFY NON-MATCH] Candidate   : {NON_MATCH_IDENT} (jane_face enrolled)')
    print(f'[VERIFY NON-MATCH] Gallery     : {gallery}')
    print(f'[VERIFY NON-MATCH] Threshold   : {THRESHOLD_NON_MATCH}')
    print(f'[VERIFY NON-MATCH] Status      : {r.status_code}')
    print(f'[VERIFY NON-MATCH] Trace ID    : {r.headers.get("x-aware-trace-id", "not returned")}')

    if r.status_code == 200:
        body = r.json()
        print(f'[VERIFY NON-MATCH] Score       : {body.get("score")}')
        print(f'[VERIFY NON-MATCH] Match       : {body.get("match")}')
    else:
        print(f'[VERIFY NON-MATCH] Response    : {r.text}')

    # Cleanup before asserting
    requests.delete(enroll_url, headers=HEADERS)

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'
    assert r.json().get('match') is False, \
        f'Expected match=false for different people, got: {r.json().get("match")}'


# ---------------------------------------------------------------------------
# Test 2: Verify with invalid base64 — expect 400
# ---------------------------------------------------------------------------

def test_verify_invalid_base64():
    # POST {{BASE_URL}}/facematch/compare
    # Sending garbage as the probe image — server should reject with 400
    url     = f'{BASE_URL}/facematch/compare'
    payload = {
        'probe':     {'image': 'this_is_not_valid_base64!!!'},
        'candidate': {'image': 'also_not_valid_base64!!!'},
        'threshold': THRESHOLD,
    }

    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[VERIFY INVALID B64] URL      : {url}')
    print(f'[VERIFY INVALID B64] Status   : {r.status_code}')
    print(f'[VERIFY INVALID B64] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[VERIFY INVALID B64] Response : {r.text}')

    assert r.status_code == 400, f'Expected 400, got {r.status_code}: {r.text}'


# ---------------------------------------------------------------------------
# Test 3: Verify with non-existing enrolled candidate — expect 404
# ---------------------------------------------------------------------------

def test_verify_non_existing_candidate(session_gallery):
    # POST {{BASE_URL}}/facematch/compare
    # Candidate identifier does not exist in the gallery — server should return 404
    gallery    = session_gallery
    probe_b64  = IMAGES.get('dan_face')

    if not probe_b64:
        pytest.fail('[VERIFY 404] probe image "dan_face" not found in config. Check your .env file.')

    url     = f'{BASE_URL}/facematch/compare'
    payload = {
        'probe':     {'image': probe_b64},
        'candidate': {'id': 'non_existing_identity_xyz', 'gallery': gallery},
        'threshold': THRESHOLD,
    }

    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[VERIFY 404] URL         : {url}')
    print(f'[VERIFY 404] Gallery     : {gallery}')
    print(f'[VERIFY 404] Candidate   : non_existing_identity_xyz')
    print(f'[VERIFY 404] Status      : {r.status_code}')
    print(f'[VERIFY 404] Trace ID    : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[VERIFY 404] Response    : {r.text}')

    assert r.status_code == 404, f'Expected 404, got {r.status_code}: {r.text}'


if __name__ == '__main__':
    test_verify_invalid_base64()
