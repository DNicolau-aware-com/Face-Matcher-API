# -*- coding: utf-8 -*-
import requests
import pytest
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, SCAN_DIRECTORY

# POST /facematch/admin/enroll/scan
# Scan a server-side directory for images and create an async enrollment job.
#
# Expected response shape:
# {
#   "jobId": "abc-123",
#   "gallery": "my_gallery",
#   "directory": "/data/images",
#   "filesFound": 150,
#   "message": "Job created with 150 images. Poll GET /facematch/admin/jobs/abc-123 for status."
# }
#
# Requires SCAN_DIRECTORY to be set in .env — this must be a path that exists
# on the server. Set it like: SCAN_DIRECTORY=/data/images

SCAN_PATTERN = '*.jpg,*.jpeg,*.png'


def test_enroll_scan(session_gallery, shared_state):
    if not SCAN_DIRECTORY:
        pytest.skip('[ENROLL SCAN] SCAN_DIRECTORY not set in .env — skipping happy-path test.')

    gallery = session_gallery
    url     = f'{BASE_URL}/facematch/admin/enroll/scan'

    payload = {
        'directory': SCAN_DIRECTORY,
        'gallery':   gallery,
        'pattern':   SCAN_PATTERN,
    }

    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[ENROLL SCAN] URL       : {url}')
    print(f'[ENROLL SCAN] Gallery   : {gallery}')
    print(f'[ENROLL SCAN] Directory : {SCAN_DIRECTORY}')
    print(f'[ENROLL SCAN] Pattern   : {SCAN_PATTERN}')
    print(f'[ENROLL SCAN] Status    : {r.status_code}')
    print(f'[ENROLL SCAN] Trace ID  : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[ENROLL SCAN] Response  : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

    body = r.json()
    assert body.get('jobId'),     f'[ENROLL SCAN] Missing jobId in response: {body}'
    assert body.get('gallery') == gallery, \
        f'[ENROLL SCAN] Expected gallery={gallery}, got: {body.get("gallery")}'
    assert body.get('directory') == SCAN_DIRECTORY, \
        f'[ENROLL SCAN] Expected directory={SCAN_DIRECTORY}, got: {body.get("directory")}'
    assert 'filesFound' in body,  f'[ENROLL SCAN] Missing filesFound in response: {body}'
    assert body.get('message'),   f'[ENROLL SCAN] Missing message in response: {body}'

    job_id = body['jobId']
    shared_state['scan_job_id'] = job_id
    print(f'[ENROLL SCAN] Job created: {job_id} — filesFound={body.get("filesFound")}')


def test_enroll_scan_missing_directory(session_gallery):
    # Omit the required 'directory' field — server returns 422 (FastAPI validation).
    url     = f'{BASE_URL}/facematch/admin/enroll/scan'
    payload = {'gallery': session_gallery}

    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[ENROLL SCAN MISSING DIR] Status   : {r.status_code}')
    print(f'[ENROLL SCAN MISSING DIR] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[ENROLL SCAN MISSING DIR] Response : {r.text}')

    assert r.status_code == 422, f'Expected 422, got {r.status_code}: {r.text}'


def test_enroll_scan_nonexistent_directory(session_gallery):
    # Directory field is present but the path does not exist on the server — expect 400.
    url     = f'{BASE_URL}/facematch/admin/enroll/scan'
    payload = {
        'directory': '/nonexistent/path/that/does/not/exist',
        'gallery':   session_gallery,
    }

    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[ENROLL SCAN BAD DIR] Status   : {r.status_code}')
    print(f'[ENROLL SCAN BAD DIR] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[ENROLL SCAN BAD DIR] Response : {r.text}')

    assert r.status_code == 400, f'Expected 400, got {r.status_code}: {r.text}'


if __name__ == '__main__':
    test_enroll_scan_missing_directory(None)
    test_enroll_scan_nonexistent_directory(None)
