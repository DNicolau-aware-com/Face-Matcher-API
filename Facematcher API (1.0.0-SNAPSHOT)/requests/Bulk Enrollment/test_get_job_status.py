# -*- coding: utf-8 -*-
import requests
import pytest
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, JOB_ID

# GET /facematch/admin/jobs/{jobId}
# Get job status and progress for a specific job.


def test_get_job_status(shared_state):
    # PRE-REQUEST: job_id chain — shared_state (from create job) → .env → fail
    job_id = shared_state.get('job_id') or JOB_ID
    if not job_id:
        pytest.fail('[GET JOB STATUS] JOB_ID is not set. Run test_create_enrollment_job first, or set JOB_ID in .env.')

    url = f'{BASE_URL}/facematch/admin/jobs/{job_id}'

    r = requests.get(url, headers=HEADERS)

    print(f'[GET JOB STATUS] URL      : {url}')
    print(f'[GET JOB STATUS] Job ID   : {job_id}')
    print(f'[GET JOB STATUS] Status   : {r.status_code}')
    print(f'[GET JOB STATUS] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[GET JOB STATUS] Response : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

    body = r.json()
    assert body.get('jobId') == job_id, \
        f'[GET JOB STATUS] Expected jobId={job_id}, got: {body.get("jobId")}'
    assert 'status' in body, \
        f'[GET JOB STATUS] Missing "status" field in response: {body}'
    assert 'progressPercent' in body, \
        f'[GET JOB STATUS] Missing "progressPercent" field in response: {body}'


def test_get_job_status_invalid_id():
    # Non-existent job ID — expect 404.
    url = f'{BASE_URL}/facematch/admin/jobs/00000000-0000-0000-0000-000000000000'

    r = requests.get(url, headers=HEADERS)

    print(f'[GET JOB STATUS INVALID] URL      : {url}')
    print(f'[GET JOB STATUS INVALID] Status   : {r.status_code}')
    print(f'[GET JOB STATUS INVALID] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[GET JOB STATUS INVALID] Response : {r.text}')

    assert r.status_code == 404, f'Expected 404, got {r.status_code}: {r.text}'


if __name__ == '__main__':
    test_get_job_status({})
    test_get_job_status_invalid_id()
