# -*- coding: utf-8 -*-
# Negative tests — 400 Bad Request and 422 Validation Error
import requests
from config import BASE_URL, HEADERS
from tests.schemas import assert_schema, APP_ERROR_SCHEMA, VALIDATION_ERROR_SCHEMA


# ── 422 Validation errors — missing / malformed request fields ────────────────

def test_400_create_gallery_missing_name():
    # POST /facematch/galleries — empty body (name required) → 422
    url = f'{BASE_URL}/facematch/galleries'
    r   = requests.post(url, headers=HEADERS, json={})

    print(f'\n[422] Create gallery — missing name')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    print(f'  Body   : {r.json()}')

    assert r.status_code == 422, f'Expected 422, got {r.status_code}: {r.text}'
    assert_schema(r.json(), VALIDATION_ERROR_SCHEMA, label='POST /facematch/galleries (missing name)')


def test_400_enroll_missing_image():
    # POST /facematch/galleries/{g}/enrollments/{id} — empty body (image required) → 422
    url = f'{BASE_URL}/facematch/galleries/employees/enrollments/test_id'
    r   = requests.post(url, headers=HEADERS, json={})

    print(f'\n[422] Enroll — missing image field')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    print(f'  Body   : {r.json()}')

    assert r.status_code == 422, f'Expected 422, got {r.status_code}: {r.text}'
    assert_schema(r.json(), VALIDATION_ERROR_SCHEMA, label='POST /facematch/galleries/{g}/enrollments/{id} (missing image)')


def test_400_search_missing_fields():
    # POST /facematch/search — empty body (probe + gallery required) → 422
    url = f'{BASE_URL}/facematch/search'
    r   = requests.post(url, headers=HEADERS, json={})

    print(f'\n[422] Search — missing required fields')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    print(f'  Body   : {r.json()}')

    assert r.status_code == 422, f'Expected 422, got {r.status_code}: {r.text}'
    assert_schema(r.json(), VALIDATION_ERROR_SCHEMA, label='POST /facematch/search (missing fields)')

    # Both probe and gallery must be flagged in the detail array
    detail = r.json()['detail']
    missing_fields = [item['loc'][-1] for item in detail]
    assert 'probe'   in missing_fields, f'"probe" not flagged in detail: {detail}'
    assert 'gallery' in missing_fields, f'"gallery" not flagged in detail: {detail}'


def test_400_verify_missing_fields():
    # POST /facematch/compare — empty body (probe + candidate required) → 422
    url = f'{BASE_URL}/facematch/compare'
    r   = requests.post(url, headers=HEADERS, json={})

    print(f'\n[422] Compare — missing required fields')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    print(f'  Body   : {r.json()}')

    assert r.status_code == 422, f'Expected 422, got {r.status_code}: {r.text}'
    assert_schema(r.json(), VALIDATION_ERROR_SCHEMA, label='POST /facematch/compare (missing fields)')

    detail = r.json()['detail']
    missing_fields = [item['loc'][-1] for item in detail]
    assert 'probe'     in missing_fields, f'"probe" not flagged in detail: {detail}'
    assert 'candidate' in missing_fields, f'"candidate" not flagged in detail: {detail}'


# ── 400 Bad Request — semantically invalid data ───────────────────────────────

def test_400_create_gallery_duplicate():
    # POST /facematch/galleries — create the same gallery twice → 400
    url     = f'{BASE_URL}/facematch/galleries'
    payload = {'name': 'bulk7'}

    requests.post(url, headers=HEADERS, json=payload)   # first call — may already exist
    r = requests.post(url, headers=HEADERS, json=payload)  # must return 400

    print(f'\n[400] Create gallery — duplicate')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    print(f'  Body   : {r.json()}')

    assert r.status_code == 400, f'Expected 400, got {r.status_code}: {r.text}'
    assert_schema(r.json(), APP_ERROR_SCHEMA, label='POST /facematch/galleries (duplicate)')


def test_400_enroll_invalid_base64_image(session_gallery):
    # POST /facematch/galleries/{g}/enrollments/{id} — invalid base64 → 400
    url = f'{BASE_URL}/facematch/galleries/{session_gallery}/enrollments/test_invalid_b64'
    r   = requests.post(url, headers=HEADERS, json={'image': 'this_is_not_valid_base64!!!'})

    print(f'\n[400] Enroll — invalid base64 image')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    print(f'  Body   : {r.json()}')

    assert r.status_code == 400, f'Expected 400, got {r.status_code}: {r.text}'
    assert_schema(r.json(), APP_ERROR_SCHEMA, label='POST /facematch/galleries/{g}/enrollments/{id} (invalid base64)')


def test_400_search_invalid_base64_image():
    # POST /facematch/search — malformed image data → 400
    url = f'{BASE_URL}/facematch/search'
    r   = requests.post(url, headers=HEADERS, json={
        'probe':         {'image': 'not_a_real_image_!!!'},
        'gallery':       'employees',
        'maxCandidates': 10,
        'threshold':     4.0,
    })

    print(f'\n[400] Search — invalid base64 image')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    print(f'  Body   : {r.json()}')

    assert r.status_code == 400, f'Expected 400, got {r.status_code}: {r.text}'
    assert_schema(r.json(), APP_ERROR_SCHEMA, label='POST /facematch/search (invalid base64)')


if __name__ == '__main__':
    test_400_create_gallery_missing_name()
    test_400_create_gallery_duplicate()
    test_400_enroll_missing_image()
    test_400_search_missing_fields()
    test_400_verify_missing_fields()
    test_400_enroll_invalid_base64_image()
    test_400_search_invalid_base64_image()
