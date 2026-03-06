# -*- coding: utf-8 -*-
# Negative tests — 400 / 422 Bad Request / validation errors
import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS

def _assert_app_error(r, expected_status):
    """App-level error: {"error": ..., "message": ...}"""
    assert r.status_code == expected_status, (
        f'Expected {expected_status}, got {r.status_code}. Body: {r.text}'
    )
    body = r.json()
    assert 'error'   in body, f'"error" key missing from response: {body}'
    assert 'message' in body, f'"message" key missing from response: {body}'
    print(f'  error   : {body.get("error")}')
    print(f'  message : {body.get("message")}')

def _assert_validation_error(r):
    """FastAPI validation error: 422 with {"detail": [...]}"""
    assert r.status_code == 422, (
        f'Expected 422 (validation error), got {r.status_code}. Body: {r.text}'
    )
    body = r.json()
    assert 'detail' in body, f'"detail" key missing from response: {body}'
    print(f'  detail  : {body.get("detail")}')

# -------------------------------------------------------------------

def test_400_create_gallery_missing_name():
    # POST {{BASE_URL}}/facematch/galleries — empty body (name required) → 422
    url = f'{BASE_URL}/facematch/galleries'
    r   = requests.post(url, headers=HEADERS, json={})

    print(f'\n[422] Create gallery — missing name')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    _assert_validation_error(r)

def test_400_create_gallery_duplicate():
    # POST {{BASE_URL}}/facematch/galleries — create the same gallery twice → 400
    url     = f'{BASE_URL}/facematch/galleries'
    payload = {'name': 'bulk7'}

    # First create (may already exist — either 200 or 400 is fine here)
    requests.post(url, headers=HEADERS, json=payload)

    # Second create must return 400
    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'\n[400] Create gallery — duplicate')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    _assert_app_error(r, 400)

def test_400_enroll_missing_image():
    # POST {{BASE_URL}}/facematch/galleries/{galleryName}/enrollments/{id} — empty body → 422
    url = f'{BASE_URL}/facematch/galleries/employees/enrollments/test_id'
    r   = requests.post(url, headers=HEADERS, json={})

    print(f'\n[422] Enroll — missing image field')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    _assert_validation_error(r)

def test_400_search_missing_fields():
    # POST {{BASE_URL}}/facematch/search — empty body → 422
    url = f'{BASE_URL}/facematch/search'
    r   = requests.post(url, headers=HEADERS, json={})

    print(f'\n[422] Search — missing required fields')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    _assert_validation_error(r)

def test_400_verify_missing_fields():
    # POST {{BASE_URL}}/facematch/compare — empty body → 422
    url = f'{BASE_URL}/facematch/compare'
    r   = requests.post(url, headers=HEADERS, json={})

    print(f'\n[422] Verify/Compare — missing required fields')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    _assert_validation_error(r)

if __name__ == '__main__':
    test_400_create_gallery_missing_name()
    test_400_create_gallery_duplicate()
    test_400_enroll_missing_image()
    test_400_search_missing_fields()
    test_400_verify_missing_fields()
