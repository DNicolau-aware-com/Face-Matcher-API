# -*- coding: utf-8 -*-
import requests
import pytest
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, IMAGES

# POST /facematch/admin/export/batch
# Batch template export (images → templates, no enrollment). Max 50 images.
#
# Expected response shape:
# {
#   "total": 2, "succeeded": 2, "failed": 0, "durationMs": 250.0,
#   "results": [
#     {"identifier": "person-001", "template": "<BASE64_TEMPLATE>", "success": true}
#   ]
# }


def test_export_batch():
    dan_image  = IMAGES.get('dan_face')
    john_image = IMAGES.get('john_face')

    if not dan_image:
        pytest.fail('[EXPORT BATCH] IMAGE_DAN_FACE not found in config. Check your .env file.')
    if not john_image:
        pytest.fail('[EXPORT BATCH] IMAGE_JOHN_FACE not found in config. Check your .env file.')

    url = f'{BASE_URL}/facematch/admin/export/batch'
    payload = {
        'images': [
            {'identifier': 'export_dan',  'image': dan_image},
            {'identifier': 'export_john', 'image': john_image},
        ]
    }

    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[EXPORT BATCH] URL      : {url}')
    print(f'[EXPORT BATCH] Images   : {len(payload["images"])}')
    print(f'[EXPORT BATCH] Status   : {r.status_code}')
    print(f'[EXPORT BATCH] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[EXPORT BATCH] Response : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

    body = r.json()
    assert body.get('total')     == 2, f'Expected total=2, got: {body.get("total")}'
    assert body.get('succeeded') == 2, f'Expected succeeded=2, got: {body.get("succeeded")}'
    assert body.get('failed')    == 0, f'Expected failed=0, got: {body.get("failed")}'

    results = body.get('results', [])
    assert len(results) == 2, f'Expected 2 result entries, got {len(results)}'

    for item in results:
        assert item.get('success') is True, \
            f'[EXPORT BATCH] Item not successful: {item}'
        assert item.get('template'), \
            f'[EXPORT BATCH] Missing template in result: {item}'

    print(f'[EXPORT BATCH] All {len(results)} templates exported successfully.')


def test_export_batch_invalid_image():
    # Send a clearly invalid (non-base64) image — expect a non-200 or a failed result entry.
    url = f'{BASE_URL}/facematch/admin/export/batch'
    payload = {
        'images': [
            {'identifier': 'bad_image', 'image': 'not_a_valid_base64_image'}
        ]
    }

    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[EXPORT BATCH INVALID] URL      : {url}')
    print(f'[EXPORT BATCH INVALID] Status   : {r.status_code}')
    print(f'[EXPORT BATCH INVALID] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[EXPORT BATCH INVALID] Response : {r.text}')

    # Server may return 400 outright, or 200 with success=false in the result entry.
    if r.status_code == 200:
        body    = r.json()
        results = body.get('results', [])
        assert len(results) == 1
        assert results[0].get('success') is False, \
            f'[EXPORT BATCH INVALID] Expected success=false for bad image, got: {results[0]}'
    else:
        assert r.status_code == 400, \
            f'[EXPORT BATCH INVALID] Expected 400 or 200+failed result, got {r.status_code}: {r.text}'


if __name__ == '__main__':
    test_export_batch()
    test_export_batch_invalid_image()
