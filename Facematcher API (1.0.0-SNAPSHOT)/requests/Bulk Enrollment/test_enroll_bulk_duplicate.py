# -*- coding: utf-8 -*-
import requests
import pytest
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, IMAGES, ensure_gallery

# Persistent gallery — intentionally NOT session_gallery so it is never deleted.
# The gallery remains populated on the Admin Dashboard after the test run.
PERSISTENT_GALLERY = 'bulk_duplicate_test'

def test_enroll_bulk_duplicate(shared_state):
    # POST {{BASE_URL}}/facematch/admin/enroll/batch-images
    # First call  → enroll ALL available images → should succeed (200)
    # Second call → same identifiers + same images → all should fail (duplicates rejected)

    gallery = ensure_gallery(PERSISTENT_GALLERY)
    url     = f'{BASE_URL}/facematch/admin/enroll/batch-images'

    # Build items from every image available in .env
    available = {k: v for k, v in IMAGES.items() if v}
    missing   = [k for k, v in IMAGES.items() if not v]

    if missing:
        print(f'[ENROLL BULK DUPLICATE] Skipping (not in .env): {", ".join(missing)}')
    if not available:
        pytest.fail('[ENROLL BULK DUPLICATE] No images found in config. Check your .env file.')

    items = [{'identifier': f'dup_{key}', 'image': b64} for key, b64 in available.items()]

    payload = {
        'items':       items,
        'gallery':     gallery,
        'storeImages': True,
    }

    print(f'[ENROLL BULK DUPLICATE] URL              : {url}')
    print(f'[ENROLL BULK DUPLICATE] Gallery          : {gallery}')
    print(f'[ENROLL BULK DUPLICATE] Images loaded    : {len(items)} ({", ".join(available.keys())})')

    # --- First attempt ---
    r1 = requests.post(url, headers=HEADERS, json=payload)

    print()
    print(f'[ENROLL BULK DUPLICATE] 1st attempt status   : {r1.status_code}')
    print(f'[ENROLL BULK DUPLICATE] 1st attempt trace ID : {r1.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[ENROLL BULK DUPLICATE] 1st attempt response : {r1.text}')

    # Accept 200 (enrolled now) or 409 (already enrolled from a previous run).
    # If 200, the body may show partial success when some were already enrolled.
    assert r1.status_code in (200, 409), \
        f'[ENROLL BULK DUPLICATE] 1st attempt: Expected 200 or 409, got {r1.status_code}: {r1.text}'

    # --- Second attempt — identical payload ---
    r2 = requests.post(url, headers=HEADERS, json=payload)

    print()
    print(f'[ENROLL BULK DUPLICATE] 2nd attempt status   : {r2.status_code}')
    print(f'[ENROLL BULK DUPLICATE] 2nd attempt trace ID : {r2.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[ENROLL BULK DUPLICATE] 2nd attempt response : {r2.text}')

    assert r2.status_code == 200, f'Expected 200, got {r2.status_code}: {r2.text}'
    body2 = r2.json()
    assert body2.get('success') is False, \
        f'[ENROLL BULK DUPLICATE] Expected success=false in body, got: {r2.text}'
    assert body2.get('enrolled') == 0, \
        f'[ENROLL BULK DUPLICATE] Expected enrolled=0, got: {body2.get("enrolled")}'
    assert body2.get('failed', 0) == len(items), \
        f'[ENROLL BULK DUPLICATE] Expected failed={len(items)}, got: {body2.get("failed")}'

    print(f'[ENROLL BULK DUPLICATE] All {len(items)} duplicates correctly rejected — '
          f'success=false, enrolled=0, failed={body2.get("failed")}')

if __name__ == '__main__':
    test_enroll_bulk_duplicate({})
