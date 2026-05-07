# -*- coding: utf-8 -*-
# Compare (1:1) — threshold/match semantics and response field validation.
import uuid
import requests
import pytest
from config import BASE_URL, HEADERS, IMAGES

IMAGE_KEY         = 'dan_face'
THRESHOLD_NORMAL  = 4.0
THRESHOLD_EXTREME = 999.0


def test_compare_match_true_same_identity():
    # Same image as both probe and candidate — score should exceed normal threshold → match=true.
    image_b64 = IMAGES.get(IMAGE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{IMAGE_KEY}" not found in config. Check your .env file.')

    url     = f'{BASE_URL}/facematch/compare'
    payload = {
        'probe':     {'image': image_b64},
        'candidate': {'image': image_b64},
        'threshold': THRESHOLD_NORMAL,
    }
    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[COMPARE MATCH TRUE] URL       : {url}')
    print(f'[COMPARE MATCH TRUE] Threshold : {THRESHOLD_NORMAL}')
    print(f'[COMPARE MATCH TRUE] Status    : {r.status_code}')
    print(f'[COMPARE MATCH TRUE] Trace ID  : {r.headers.get("x-aware-trace-id", "not returned")}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'
    body = r.json()
    print(f'[COMPARE MATCH TRUE] Score     : {body.get("score")}')
    print(f'[COMPARE MATCH TRUE] Match     : {body.get("match")}')

    assert 'score' in body, f'"score" key missing from compare response: {body}'
    assert 'match' in body, f'"match" key missing from compare response: {body}'
    assert body.get('match') is True, \
        f'Expected match=true for same image at threshold={THRESHOLD_NORMAL}, got: {body}'


def test_compare_match_false_extreme_threshold():
    # Same image, extreme threshold — score < threshold → match=false.
    image_b64 = IMAGES.get(IMAGE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{IMAGE_KEY}" not found in config. Check your .env file.')

    url     = f'{BASE_URL}/facematch/compare'
    payload = {
        'probe':     {'image': image_b64},
        'candidate': {'image': image_b64},
        'threshold': THRESHOLD_EXTREME,
    }
    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[COMPARE MATCH FALSE] URL       : {url}')
    print(f'[COMPARE MATCH FALSE] Threshold : {THRESHOLD_EXTREME}')
    print(f'[COMPARE MATCH FALSE] Status    : {r.status_code}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'
    body = r.json()
    print(f'[COMPARE MATCH FALSE] Score     : {body.get("score")}')
    print(f'[COMPARE MATCH FALSE] Match     : {body.get("match")}')

    assert body.get('match') is False, \
        f'Expected match=false with threshold={THRESHOLD_EXTREME}, got: {body}'


def test_compare_response_fields_present():
    # Response must contain both "score" and "match" regardless of result.
    image_b64 = IMAGES.get(IMAGE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{IMAGE_KEY}" not found in config. Check your .env file.')

    url     = f'{BASE_URL}/facematch/compare'
    payload = {
        'probe':     {'image': image_b64},
        'candidate': {'image': image_b64},
        'threshold': THRESHOLD_NORMAL,
    }
    r    = requests.post(url, headers=HEADERS, json=payload)
    body = r.json()

    print(f'[COMPARE FIELDS] Status : {r.status_code}')
    print(f'[COMPARE FIELDS] Body   : {body}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'
    assert 'score' in body, f'"score" key missing from compare response: {body}'
    assert 'match' in body, f'"match" key missing from compare response: {body}'
    assert isinstance(body.get('score'), (int, float)), \
        f'"score" should be numeric, got: {type(body.get("score"))}'
    assert isinstance(body.get('match'), bool), \
        f'"match" should be boolean, got: {type(body.get("match"))}'


def test_compare_score_consistent_with_match(session_gallery):
    # score >= threshold must mean match=true; score < threshold must mean match=false.
    # Test both conditions against the same enrolled identity.
    gallery   = session_gallery
    ident     = f'cmp_thresh_{uuid.uuid4().hex[:8]}'
    image_b64 = IMAGES.get(IMAGE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{IMAGE_KEY}" not found in config. Check your .env file.')

    enroll_r = requests.post(
        f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ident}',
        headers=HEADERS,
        json={'image': image_b64},
    )
    assert enroll_r.status_code == 200, f'Pre-enroll failed: {enroll_r.status_code}: {enroll_r.text}'

    url = f'{BASE_URL}/facematch/compare'

    # Low threshold — should match
    r_low = requests.post(url, headers=HEADERS, json={
        'probe':     {'image': image_b64},
        'candidate': {'id': ident, 'gallery': gallery},
        'threshold': THRESHOLD_NORMAL,
    })
    # High threshold — should not match
    r_high = requests.post(url, headers=HEADERS, json={
        'probe':     {'image': image_b64},
        'candidate': {'id': ident, 'gallery': gallery},
        'threshold': THRESHOLD_EXTREME,
    })

    requests.delete(
        f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ident}',
        headers=HEADERS,
    )

    assert r_low.status_code == 200, f'Low-threshold compare failed: {r_low.status_code}: {r_low.text}'
    assert r_high.status_code == 200, f'High-threshold compare failed: {r_high.status_code}: {r_high.text}'

    body_low  = r_low.json()
    body_high = r_high.json()

    print(f'[COMPARE CONSISTENCY] Low  threshold={THRESHOLD_NORMAL}  score={body_low.get("score")}  match={body_low.get("match")}')
    print(f'[COMPARE CONSISTENCY] High threshold={THRESHOLD_EXTREME} score={body_high.get("score")} match={body_high.get("match")}')

    assert body_low.get('match') is True, \
        f'Expected match=true at threshold={THRESHOLD_NORMAL}, got: {body_low}'
    assert body_high.get('match') is False, \
        f'Expected match=false at threshold={THRESHOLD_EXTREME}, got: {body_high}'
    assert body_low.get('score') == body_high.get('score'), \
        'Score should be identical regardless of threshold for the same pair'


if __name__ == '__main__':
    test_compare_match_true_same_identity()
    test_compare_match_false_extreme_threshold()
    test_compare_response_fields_present()
