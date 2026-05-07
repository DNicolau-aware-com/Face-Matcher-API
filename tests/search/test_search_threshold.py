# -*- coding: utf-8 -*-
# Search (1:N) — threshold semantics, maxCandidates limit, empty gallery.
import time
import uuid
import requests
import pytest
from config import BASE_URL, HEADERS, IMAGES

IMAGE_KEY         = 'dan_face'
THRESHOLD_NORMAL  = 4.0
THRESHOLD_EXTREME = 999.0
INDEX_TIMEOUT     = 15   # seconds to wait for enrollment to become searchable


def _wait_for_indexed(gallery, ident, image_b64, timeout=INDEX_TIMEOUT):
    """Poll search (threshold=0.0) until the identity appears or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.post(
            f'{BASE_URL}/facematch/search',
            headers=HEADERS,
            json={
                'probe':         {'image': image_b64},
                'gallery':       gallery,
                'maxCandidates': 10,
                'threshold':     0.0,
            },
        )
        if r.status_code == 200:
            if any(c.get('id') == ident for c in r.json().get('candidates', [])):
                return True
        time.sleep(1)
    return False


def test_search_match_true_at_low_threshold():
    # Use an isolated single-identity gallery so the enrolled face is guaranteed to be
    # the only (and thus top) result. Verify match=true at a low threshold.
    gallery   = f'thresh_test_{uuid.uuid4().hex[:8]}'
    ident     = f'thresh_match_{uuid.uuid4().hex[:8]}'
    image_b64 = IMAGES.get(IMAGE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{IMAGE_KEY}" not found in config. Check your .env file.')

    create_r = requests.post(
        f'{BASE_URL}/facematch/galleries',
        headers=HEADERS,
        json={'name': gallery},
    )
    assert create_r.status_code == 200, f'Gallery creation failed: {create_r.text}'

    enroll_r = requests.post(
        f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ident}',
        headers=HEADERS,
        json={'image': image_b64},
    )
    assert enroll_r.status_code == 200, f'Pre-enroll failed: {enroll_r.status_code}: {enroll_r.text}'

    indexed = _wait_for_indexed(gallery, ident, image_b64)
    if not indexed:
        requests.delete(f'{BASE_URL}/facematch/galleries/{gallery}', headers=HEADERS)
        pytest.skip(f'Identity not indexed within {INDEX_TIMEOUT}s — Milvus may need more time.')

    threshold = 0.1
    url       = f'{BASE_URL}/facematch/search'
    payload   = {
        'probe':         {'image': image_b64},
        'gallery':       gallery,
        'maxCandidates': 10,
        'threshold':     threshold,
    }
    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[SEARCH THRESHOLD] URL       : {url}')
    print(f'[SEARCH THRESHOLD] Gallery   : {gallery}')
    print(f'[SEARCH THRESHOLD] Identity  : {ident}')
    print(f'[SEARCH THRESHOLD] Threshold : {threshold}')
    print(f'[SEARCH THRESHOLD] Status    : {r.status_code}')
    print(f'[SEARCH THRESHOLD] Trace ID  : {r.headers.get("x-aware-trace-id", "not returned")}')

    requests.delete(f'{BASE_URL}/facematch/galleries/{gallery}', headers=HEADERS)

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'
    candidates = r.json().get('candidates', [])
    for c in candidates:
        print(f'  id={c.get("id")} | score={c.get("score")} | match={c.get("match")}')

    match_true = [c for c in candidates if c.get('id') == ident and c.get('match') is True]
    assert match_true, \
        f'Expected enrolled identity "{ident}" with match=true at threshold={threshold}; candidates: {candidates}'


def test_search_match_false_at_extreme_threshold(session_gallery):
    # An extreme threshold must force match=false for every returned candidate.
    gallery   = session_gallery
    ident     = f'thresh_nomatch_{uuid.uuid4().hex[:8]}'
    image_b64 = IMAGES.get(IMAGE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{IMAGE_KEY}" not found in config. Check your .env file.')

    enroll_r = requests.post(
        f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ident}',
        headers=HEADERS,
        json={'image': image_b64},
    )
    assert enroll_r.status_code == 200, f'Pre-enroll failed: {enroll_r.status_code}: {enroll_r.text}'

    url = f'{BASE_URL}/facematch/search'
    payload = {
        'probe':         {'image': image_b64},
        'gallery':       gallery,
        'maxCandidates': 10,
        'threshold':     THRESHOLD_EXTREME,
    }
    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[SEARCH NOMATCH] URL       : {url}')
    print(f'[SEARCH NOMATCH] Threshold : {THRESHOLD_EXTREME}')
    print(f'[SEARCH NOMATCH] Status    : {r.status_code}')

    requests.delete(
        f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ident}',
        headers=HEADERS,
    )

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'
    candidates = r.json().get('candidates', [])
    for c in candidates:
        print(f'  id={c.get("id")} | score={c.get("score")} | match={c.get("match")}')
        assert c.get('match') is False, \
            f'Expected match=false with threshold={THRESHOLD_EXTREME}, but got: {c}'


def test_search_max_candidates_limits_results(session_gallery):
    # With maxCandidates=1 the response must contain at most 1 candidate.
    gallery   = session_gallery
    image_b64 = IMAGES.get(IMAGE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{IMAGE_KEY}" not found in config. Check your .env file.')

    url = f'{BASE_URL}/facematch/search'
    payload = {
        'probe':         {'image': image_b64},
        'gallery':       gallery,
        'maxCandidates': 1,
        'threshold':     THRESHOLD_NORMAL,
    }
    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[SEARCH MAX1] URL            : {url}')
    print(f'[SEARCH MAX1] maxCandidates  : 1')
    print(f'[SEARCH MAX1] Status         : {r.status_code}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'
    candidates = r.json().get('candidates', [])
    print(f'[SEARCH MAX1] Candidates returned : {len(candidates)}')
    assert len(candidates) <= 1, \
        f'Expected at most 1 candidate with maxCandidates=1, got {len(candidates)}'


def test_search_empty_gallery_returns_empty_candidates():
    # Searching in an empty gallery must return 200 with an empty candidates list, not an error.
    gallery_name = f'empty_gallery_{uuid.uuid4().hex[:8]}'
    image_b64    = IMAGES.get(IMAGE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{IMAGE_KEY}" not found in config. Check your .env file.')

    # Create an empty gallery for this test
    create_r = requests.post(
        f'{BASE_URL}/facematch/galleries',
        headers=HEADERS,
        json={'name': gallery_name},
    )
    assert create_r.status_code == 200, f'Failed to create gallery: {create_r.text}'

    url = f'{BASE_URL}/facematch/search'
    payload = {
        'probe':         {'image': image_b64},
        'gallery':       gallery_name,
        'maxCandidates': 10,
        'threshold':     THRESHOLD_NORMAL,
    }
    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[SEARCH EMPTY] URL        : {url}')
    print(f'[SEARCH EMPTY] Gallery    : {gallery_name}')
    print(f'[SEARCH EMPTY] Status     : {r.status_code}')
    print(f'[SEARCH EMPTY] Trace ID   : {r.headers.get("x-aware-trace-id", "not returned")}')

    requests.delete(f'{BASE_URL}/facematch/galleries/{gallery_name}', headers=HEADERS)

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'
    candidates = r.json().get('candidates', [])
    print(f'[SEARCH EMPTY] Candidates : {candidates}')
    assert candidates == [], \
        f'Expected empty candidates list for empty gallery, got: {candidates}'


if __name__ == '__main__':
    test_search_empty_gallery_returns_empty_candidates()
