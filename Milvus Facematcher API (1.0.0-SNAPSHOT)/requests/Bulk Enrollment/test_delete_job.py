# -*- coding: utf-8 -*-
import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
import pytest
from config import BASE_URL, HEADERS, JOB_ID

def test_delete_job(shared_state):
    # PRE-REQUEST: job_id chain — shared_state (from create job) → .env → fail
    job_id = shared_state.get('job_id') or JOB_ID
    if not job_id:
        pytest.fail('[DELETE JOB] JOB_ID is not set. Run test_create_enrollment_job first, or set JOB_ID in .env.')

    # DELETE {{BASE_URL}}/facematch/admin/jobs/{jobId}
    url = f'{BASE_URL}/facematch/admin/jobs/{job_id}'

    r = requests.delete(url, headers=HEADERS)

    print(f'[DELETE JOB] URL      : {url}')
    print(f'[DELETE JOB] Job ID   : {job_id}')
    print(f'[DELETE JOB] Status   : {r.status_code}')
    print(f'[DELETE JOB] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[DELETE JOB] Response : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

def test_delete_job_invalid_id():
    # DELETE {{BASE_URL}}/facematch/admin/jobs/{jobId} — non-existent job ID
    url = f'{BASE_URL}/facematch/admin/jobs/00000000-0000-0000-0000-000000000000'

    r = requests.delete(url, headers=HEADERS)

    print(f'[DELETE JOB INVALID] URL      : {url}')
    print(f'[DELETE JOB INVALID] Status   : {r.status_code}')
    print(f'[DELETE JOB INVALID] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[DELETE JOB INVALID] Response : {r.text}')

    assert r.status_code == 404, f'Expected 404, got {r.status_code}: {r.text}'

if __name__ == '__main__':
    test_delete_job()
    test_delete_job_invalid_id()
