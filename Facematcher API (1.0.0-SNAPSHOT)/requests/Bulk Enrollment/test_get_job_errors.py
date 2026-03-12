# -*- coding: utf-8 -*-
import requests
import pytest
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, JOB_ID

# GET /facematch/admin/jobs/{jobId}/errors
# Get failed items for a job. Query params: limit (default 100, max 1000).


def test_get_job_errors(shared_state):
    # PRE-REQUEST: job_id chain — shared_state (from create job) → .env → fail
    job_id = shared_state.get('job_id') or JOB_ID
    if not job_id:
        pytest.fail('[GET JOB ERRORS] JOB_ID is not set. Run test_create_enrollment_job first, or set JOB_ID in .env.')

    url = f'{BASE_URL}/facematch/admin/jobs/{job_id}/errors'

    r = requests.get(url, headers=HEADERS)

    print(f'[GET JOB ERRORS] URL      : {url}')
    print(f'[GET JOB ERRORS] Job ID   : {job_id}')
    print(f'[GET JOB ERRORS] Status   : {r.status_code}')
    print(f'[GET JOB ERRORS] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[GET JOB ERRORS] Response : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'


def test_get_job_errors_with_limit(shared_state):
    # Same endpoint with explicit limit query param.
    job_id = shared_state.get('job_id') or JOB_ID
    if not job_id:
        pytest.fail('[GET JOB ERRORS LIMIT] JOB_ID is not set. Run test_create_enrollment_job first, or set JOB_ID in .env.')

    url = f'{BASE_URL}/facematch/admin/jobs/{job_id}/errors'
    params = {'limit': 10}

    r = requests.get(url, headers=HEADERS, params=params)

    print(f'[GET JOB ERRORS LIMIT] URL      : {url}')
    print(f'[GET JOB ERRORS LIMIT] Job ID   : {job_id}')
    print(f'[GET JOB ERRORS LIMIT] Limit    : {params["limit"]}')
    print(f'[GET JOB ERRORS LIMIT] Status   : {r.status_code}')
    print(f'[GET JOB ERRORS LIMIT] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[GET JOB ERRORS LIMIT] Response : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'


def test_get_job_errors_invalid_id():
    # Non-existent job ID — expect 404.
    url = f'{BASE_URL}/facematch/admin/jobs/00000000-0000-0000-0000-000000000000/errors'

    r = requests.get(url, headers=HEADERS)

    print(f'[GET JOB ERRORS INVALID] URL      : {url}')
    print(f'[GET JOB ERRORS INVALID] Status   : {r.status_code}')
    print(f'[GET JOB ERRORS INVALID] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[GET JOB ERRORS INVALID] Response : {r.text}')

    assert r.status_code == 404, f'Expected 404, got {r.status_code}: {r.text}'


if __name__ == '__main__':
    test_get_job_errors({})
    test_get_job_errors_with_limit({})
    test_get_job_errors_invalid_id()
