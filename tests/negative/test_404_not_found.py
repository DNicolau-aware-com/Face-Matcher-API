# -*- coding: utf-8 -*-
# Negative tests — 404 Not Found
import requests
from config import BASE_URL, HEADERS
from tests.schemas import assert_schema, APP_ERROR_SCHEMA, VALIDATE_GALLERY_SCHEMA

NONEXISTENT_GALLERY    = 'gallery_does_not_exist_xyz'
NONEXISTENT_IDENTIFIER = 'identifier_does_not_exist_xyz'


# ── 404 — resource not found ──────────────────────────────────────────────────

def test_404_delete_nonexistent_gallery():
    # DELETE /facematch/galleries/{galleryName} — gallery does not exist → 404
    url = f'{BASE_URL}/facematch/galleries/{NONEXISTENT_GALLERY}'
    r   = requests.delete(url, headers=HEADERS)

    print(f'\n[404] Delete gallery — not found')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    print(f'  Body   : {r.json()}')

    assert r.status_code == 404, f'Expected 404, got {r.status_code}: {r.text}'
    assert_schema(r.json(), APP_ERROR_SCHEMA, label='DELETE /facematch/galleries/{g} (not found)')


def test_404_delete_nonexistent_enrollment():
    # DELETE /facematch/galleries/{g}/enrollments/{id} — neither exists → 404
    url = f'{BASE_URL}/facematch/galleries/{NONEXISTENT_GALLERY}/enrollments/{NONEXISTENT_IDENTIFIER}'
    r   = requests.delete(url, headers=HEADERS)

    print(f'\n[404] Delete enrollment — not found')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    print(f'  Body   : {r.json()}')

    assert r.status_code == 404, f'Expected 404, got {r.status_code}: {r.text}'
    assert_schema(r.json(), APP_ERROR_SCHEMA, label='DELETE /facematch/galleries/{g}/enrollments/{id} (not found)')


def test_404_enroll_nonexistent_gallery():
    # POST /facematch/galleries/{g}/enrollments/{id} — gallery does not exist → 404
    from config import IMAGES
    import pytest
    image_b64 = next((v for v in IMAGES.values() if v), None)
    if not image_b64:
        pytest.fail('No image found in config.')

    url = f'{BASE_URL}/facematch/galleries/{NONEXISTENT_GALLERY}/enrollments/test_enroll_id'
    r   = requests.post(url, headers=HEADERS, json={'image': image_b64})

    print(f'\n[404] Enroll — gallery not found')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    print(f'  Body   : {r.json()}')

    assert r.status_code == 404, f'Expected 404, got {r.status_code}: {r.text}'
    assert_schema(r.json(), APP_ERROR_SCHEMA, label='POST /facematch/galleries/{g}/enrollments/{id} (gallery not found)')


def test_404_search_valid_image_nonexistent_gallery():
    # POST /facematch/search — valid image, gallery does not exist → 404
    from config import IMAGES
    import pytest
    image_b64 = IMAGES.get('dan_face') or next((v for v in IMAGES.values() if v), None)
    if not image_b64:
        pytest.fail('No image found in config.')

    url = f'{BASE_URL}/facematch/search'
    r   = requests.post(url, headers=HEADERS, json={
        'probe':         {'image': image_b64},
        'gallery':       NONEXISTENT_GALLERY,
        'maxCandidates': 10,
        'threshold':     4.0,
    })

    print(f'\n[404] Search — valid image, gallery not found')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    print(f'  Body   : {r.json()}')

    assert r.status_code == 404, f'Expected 404, got {r.status_code}: {r.text}'
    assert_schema(r.json(), APP_ERROR_SCHEMA, label='POST /facematch/search (gallery not found)')


def test_404_get_nonexistent_job():
    # GET /facematch/admin/jobs/{jobId} — job does not exist → 404
    url = f'{BASE_URL}/facematch/admin/jobs/job_does_not_exist_xyz'
    r   = requests.get(url, headers=HEADERS)

    print(f'\n[404] Get job status — not found')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    print(f'  Body   : {r.json()}')

    assert r.status_code == 404, f'Expected 404, got {r.status_code}: {r.text}'
    assert_schema(r.json(), APP_ERROR_SCHEMA, label='GET /facematch/admin/jobs/{id} (not found)')


# ── 400 — image validation fires before gallery lookup ────────────────────────

def test_404_search_invalid_image_nonexistent_gallery():
    # POST /facematch/search — invalid image → 400 (image validation runs before gallery lookup)
    url = f'{BASE_URL}/facematch/search'
    r   = requests.post(url, headers=HEADERS, json={
        'probe':         {'image': 'ZmFrZWltYWdl'},
        'gallery':       NONEXISTENT_GALLERY,
        'maxCandidates': 10,
        'threshold':     4.0,
    })

    print(f'\n[400] Search — invalid probe image (validation before gallery lookup)')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    print(f'  Body   : {r.json()}')

    assert r.status_code == 400, f'Expected 400, got {r.status_code}: {r.text}'
    assert_schema(r.json(), APP_ERROR_SCHEMA, label='POST /facematch/search (invalid image, pre-gallery validation)')


# ── 200 — validate endpoint returns counts even for nonexistent gallery ───────

def test_404_validate_nonexistent_gallery():
    # GET /facematch/admin/validate/{gallery} — gallery does not exist → 200 (all counts = 0)
    url = f'{BASE_URL}/facematch/admin/validate/{NONEXISTENT_GALLERY}'
    r   = requests.get(url, headers=HEADERS)

    print(f'\n[200] Validate gallery — not found (returns 200 with zero counts)')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    print(f'  Body   : {r.json()}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'
    body = r.json()
    assert_schema(body, VALIDATE_GALLERY_SCHEMA, label='GET /facematch/admin/validate/{g} (nonexistent)')

    assert body['gallery']      == NONEXISTENT_GALLERY, f'gallery name mismatch: {body["gallery"]}'
    assert body['sqlCount']     == 0, f'sqlCount should be 0 for nonexistent gallery: {body["sqlCount"]}'
    assert body['milvusCount']  == 0, f'milvusCount should be 0 for nonexistent gallery: {body["milvusCount"]}'
    assert body['missingIds']   == [], f'missingIds should be [] for nonexistent gallery: {body["missingIds"]}'
    assert body['orphanIds']    == [], f'orphanIds should be [] for nonexistent gallery: {body["orphanIds"]}'


if __name__ == '__main__':
    test_404_delete_nonexistent_gallery()
    test_404_delete_nonexistent_enrollment()
    test_404_enroll_nonexistent_gallery()
    test_404_search_valid_image_nonexistent_gallery()
    test_404_get_nonexistent_job()
    test_404_search_invalid_image_nonexistent_gallery()
    test_404_validate_nonexistent_gallery()
