# -*- coding: utf-8 -*-
# Upload endpoints — error cases (all happy-path upload tests are in other files).
import base64
import requests
import pytest
from config import BASE_URL, HEADERS, IMAGES

NONEXISTENT_GALLERY = 'gallery_does_not_exist_xyz'
NONEXISTENT_ID      = 'identifier_does_not_exist_xyz'

UPLOAD_HEADERS = {k: v for k, v in HEADERS.items() if k.lower() != 'content-type'}


def _image_bytes(key='dan_face'):
    b64 = IMAGES.get(key)
    if not b64:
        pytest.fail(f'Image key "{key}" not found in config. Check your .env file.')
    return base64.b64decode(b64)


def test_upload_enroll_nonexistent_gallery():
    # POST /facematch/upload/galleries/{gallery}/enrollments/{id} — gallery does not exist → 404
    url = f'{BASE_URL}/facematch/upload/galleries/{NONEXISTENT_GALLERY}/enrollments/test_id'
    r   = requests.post(
        url,
        headers=UPLOAD_HEADERS,
        files={'image': ('probe.jpg', _image_bytes(), 'image/jpeg')},
    )

    print(f'[UPLOAD ENROLL 404] URL    : {url}')
    print(f'[UPLOAD ENROLL 404] Status : {r.status_code}')
    print(f'[UPLOAD ENROLL 404] Body   : {r.text}')

    assert r.status_code == 404, f'Expected 404, got {r.status_code}: {r.text}'
    body = r.json()
    assert 'error'   in body, f'"error" key missing: {body}'
    assert 'message' in body, f'"message" key missing: {body}'


def test_upload_search_nonexistent_gallery():
    # POST /facematch/upload/search — valid image, non-existent gallery → 404
    url = f'{BASE_URL}/facematch/upload/search'
    r   = requests.post(
        url,
        headers=UPLOAD_HEADERS,
        files={'image': ('probe.jpg', _image_bytes(), 'image/jpeg')},
        data={
            'gallery':        NONEXISTENT_GALLERY,
            'max_candidates': 10,
            'threshold':      4.0,
        },
    )

    print(f'[UPLOAD SEARCH 404] URL    : {url}')
    print(f'[UPLOAD SEARCH 404] Status : {r.status_code}')
    print(f'[UPLOAD SEARCH 404] Body   : {r.text}')

    assert r.status_code == 404, f'Expected 404, got {r.status_code}: {r.text}'
    body = r.json()
    assert 'error'   in body, f'"error" key missing: {body}'
    assert 'message' in body, f'"message" key missing: {body}'


def test_upload_compare_nonexistent_candidate(session_gallery):
    # POST /facematch/upload/compare — candidate_id does not exist in the gallery → 404
    gallery = session_gallery
    url     = f'{BASE_URL}/facematch/upload/compare'
    r       = requests.post(
        url,
        headers=UPLOAD_HEADERS,
        files={'probe_image': ('probe.jpg', _image_bytes(), 'image/jpeg')},
        data={
            'candidate_id':      NONEXISTENT_ID,
            'candidate_gallery': gallery,
            'threshold':         4.0,
        },
    )

    print(f'[UPLOAD COMPARE 404] URL    : {url}')
    print(f'[UPLOAD COMPARE 404] Status : {r.status_code}')
    print(f'[UPLOAD COMPARE 404] Body   : {r.text}')

    assert r.status_code == 404, f'Expected 404, got {r.status_code}: {r.text}'
    body = r.json()
    assert 'error'   in body, f'"error" key missing: {body}'
    assert 'message' in body, f'"message" key missing: {body}'


if __name__ == '__main__':
    test_upload_search_nonexistent_gallery()
