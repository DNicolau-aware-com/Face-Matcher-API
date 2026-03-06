# -*- coding: utf-8 -*-
# Negative tests — 404 Resource not found
import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS

NONEXISTENT_GALLERY    = 'gallery_does_not_exist_xyz'
NONEXISTENT_IDENTIFIER = 'identifier_does_not_exist_xyz'

def _assert_error_format(r, expected_status):
    """Validate the standard error response format."""
    assert r.status_code == expected_status, (
        f'Expected {expected_status}, got {r.status_code}. Body: {r.text}'
    )
    body = r.json()
    assert 'error'   in body, f'"error" key missing from response: {body}'
    assert 'message' in body, f'"message" key missing from response: {body}'
    print(f'  error   : {body.get("error")}')
    print(f'  message : {body.get("message")}')

# -------------------------------------------------------------------

def test_404_delete_nonexistent_gallery():
    # DELETE {{BASE_URL}}/facematch/galleries/{galleryName} — gallery does not exist → 404
    url = f'{BASE_URL}/facematch/galleries/{NONEXISTENT_GALLERY}'
    r   = requests.delete(url, headers=HEADERS)

    print(f'\n[404] Delete gallery — not found')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    _assert_error_format(r, 404)

def test_404_delete_nonexistent_enrollment():
    # DELETE {{BASE_URL}}/facematch/galleries/{galleryName}/enrollments/{id} — not found
    url = f'{BASE_URL}/facematch/galleries/{NONEXISTENT_GALLERY}/enrollments/{NONEXISTENT_IDENTIFIER}'
    r   = requests.delete(url, headers=HEADERS)

    print(f'\n[404] Delete enrollment — gallery or enrollment not found')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    _assert_error_format(r, 404)

def test_404_search_nonexistent_gallery():
    # POST {{BASE_URL}}/facematch/search — invalid image → 400 (image validation runs before gallery lookup)
    url     = f'{BASE_URL}/facematch/search'
    payload = {
        'probe':         {'image': 'ZmFrZWltYWdl'},  # dummy base64
        'gallery':       NONEXISTENT_GALLERY,
        'maxCandidates': 10,
        'threshold':     4.0,
    }
    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'\n[400] Search — invalid probe image (validation before gallery lookup)')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    _assert_error_format(r, 400)

def test_404_validate_nonexistent_gallery():
    # GET {{BASE_URL}}/facematch/admin/validate/{gallery} — gallery does not exist → 200 (returns empty counts)
    url = f'{BASE_URL}/facematch/admin/validate/{NONEXISTENT_GALLERY}'
    r   = requests.get(url, headers=HEADERS)

    print(f'\n[200] Validate gallery — not found (returns 200 with zero counts)')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'
    body = r.json()
    assert 'gallery' in body, f'"gallery" key missing: {body}'
    print(f'  gallery       : {body.get("gallery")}')
    print(f'  sqlCount      : {body.get("sqlCount")}')
    print(f'  milvusCount   : {body.get("milvusCount")}')

def test_404_get_nonexistent_job():
    # GET {{BASE_URL}}/facematch/admin/jobs/{jobId} — job does not exist
    url = f'{BASE_URL}/facematch/admin/jobs/job_does_not_exist_xyz'
    r   = requests.get(url, headers=HEADERS)

    print(f'\n[404] Get job status — not found')
    print(f'  URL    : {url}')
    print(f'  Status : {r.status_code}')
    _assert_error_format(r, 404)

if __name__ == '__main__':
    test_404_delete_nonexistent_gallery()
    test_404_delete_nonexistent_enrollment()
    test_404_search_nonexistent_gallery()
    test_404_validate_nonexistent_gallery()
    test_404_get_nonexistent_job()
