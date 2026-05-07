# -*- coding: utf-8 -*-
# Enforce documented batch-size limits:
#   POST /facematch/admin/enroll/batch-images → max 50 items
#   POST /facematch/admin/export/batch        → max 50 images
#   POST /facematch/admin/jobs                → max 500 items
import requests
import pytest
from config import BASE_URL, HEADERS, IMAGES

IMAGE_KEY = 'dan_face'


def _get_image():
    img = IMAGES.get(IMAGE_KEY)
    if not img:
        pytest.fail(f'Image key "{IMAGE_KEY}" not found in config. Check your .env file.')
    return img


def test_batch_images_over_limit(session_gallery):
    # 51 items must be rejected (max is 50).
    gallery   = session_gallery
    image_b64 = _get_image()
    items     = [{'identifier': f'over_limit_{i}', 'image': image_b64} for i in range(51)]

    url = f'{BASE_URL}/facematch/admin/enroll/batch-images'
    r   = requests.post(url, headers=HEADERS, json={
        'items':       items,
        'gallery':     gallery,
        'storeImages': False,
    })

    print(f'[BATCH LIMIT] batch-images 51 items → status {r.status_code}')
    print(f'[BATCH LIMIT] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[BATCH LIMIT] Response : {r.text[:300]}')

    assert r.status_code in (400, 422), \
        f'Expected 400 or 422 for 51 items (limit 50), got {r.status_code}: {r.text}'


def test_export_batch_over_limit():
    # 51 images must be rejected (max is 50).
    image_b64 = _get_image()
    images    = [{'identifier': f'over_export_{i}', 'image': image_b64} for i in range(51)]

    url = f'{BASE_URL}/facematch/admin/export/batch'
    r   = requests.post(url, headers=HEADERS, json={'images': images})

    print(f'[EXPORT LIMIT] export/batch 51 images → status {r.status_code}')
    print(f'[EXPORT LIMIT] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[EXPORT LIMIT] Response : {r.text[:300]}')

    assert r.status_code in (400, 422), \
        f'Expected 400 or 422 for 51 images (limit 50), got {r.status_code}: {r.text}'


def test_create_job_over_limit(session_gallery):
    # 501 items must be rejected (max is 500).
    gallery   = session_gallery
    image_b64 = _get_image()
    items     = [{'identifier': f'over_job_{i}', 'image': image_b64} for i in range(501)]

    url = f'{BASE_URL}/facematch/admin/jobs'
    r   = requests.post(url, headers=HEADERS, json={
        'items':   items,
        'gallery': gallery,
    })

    print(f'[JOB LIMIT] admin/jobs 501 items → status {r.status_code}')
    print(f'[JOB LIMIT] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[JOB LIMIT] Response : {r.text[:300]}')

    assert r.status_code in (400, 422), \
        f'Expected 400 or 422 for 501 items (limit 500), got {r.status_code}: {r.text}'


if __name__ == '__main__':
    test_export_batch_over_limit()
