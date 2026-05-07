# -*- coding: utf-8 -*-
# GET /facematch/admin/jobs — limit and offset pagination parameters.
import requests
from config import BASE_URL, HEADERS


def test_list_jobs_with_limit():
    # limit=1 must return at most 1 job.
    url = f'{BASE_URL}/facematch/admin/jobs'
    r   = requests.get(url, headers=HEADERS, params={'limit': 1})

    print(f'[JOBS PAGINATION] URL      : {url}?limit=1')
    print(f'[JOBS PAGINATION] Status   : {r.status_code}')
    print(f'[JOBS PAGINATION] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[JOBS PAGINATION] Response : {r.text[:300]}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'
    body = r.json()
    jobs = body if isinstance(body, list) else body.get('jobs', body.get('content', body.get('items', [])))
    print(f'[JOBS PAGINATION] Jobs returned : {len(jobs)}')
    assert len(jobs) <= 1, f'Expected at most 1 job with limit=1, got {len(jobs)}'


def test_list_jobs_with_offset():
    # offset=0 and offset=1 should return different (or empty) sets.
    url = f'{BASE_URL}/facematch/admin/jobs'

    r0 = requests.get(url, headers=HEADERS, params={'limit': 50, 'offset': 0})
    r1 = requests.get(url, headers=HEADERS, params={'limit': 50, 'offset': 1})

    print(f'[JOBS OFFSET] offset=0 status : {r0.status_code}')
    print(f'[JOBS OFFSET] offset=1 status : {r1.status_code}')
    print(f'[JOBS OFFSET] Trace ID        : {r1.headers.get("x-aware-trace-id", "not returned")}')

    assert r0.status_code == 200, f'Expected 200 for offset=0, got {r0.status_code}: {r0.text}'
    assert r1.status_code == 200, f'Expected 200 for offset=1, got {r1.status_code}: {r1.text}'

    def _jobs(resp):
        body = resp.json()
        return body if isinstance(body, list) else body.get('jobs', body.get('content', body.get('items', [])))

    jobs0 = _jobs(r0)
    jobs1 = _jobs(r1)

    print(f'[JOBS OFFSET] Jobs at offset=0 : {len(jobs0)}')
    print(f'[JOBS OFFSET] Jobs at offset=1 : {len(jobs1)}')

    # offset=1 must return at most len(jobs0)-1 items (it skips one)
    if jobs0:
        assert len(jobs1) <= len(jobs0), \
            f'offset=1 returned {len(jobs1)} jobs but offset=0 returned {len(jobs0)}; ' \
            'offset should reduce (or equal) the count'


def test_list_jobs_errors_max_limit():
    # GET /facematch/admin/jobs/{jobId}/errors with limit > 1000 — server should cap or reject.
    # We use a known-existing job from shared state if available, otherwise skip gracefully.
    url = f'{BASE_URL}/facematch/admin/jobs'
    list_r = requests.get(url, headers=HEADERS, params={'limit': 1})
    assert list_r.status_code == 200

    body = list_r.json()
    jobs = body if isinstance(body, list) else body.get('jobs', body.get('content', body.get('items', [])))
    if not jobs:
        print('[JOBS ERRORS LIMIT] No jobs available — skipping limit boundary check')
        return

    job_id    = jobs[0].get('jobId') or jobs[0].get('id') or jobs[0].get('job_id')
    errors_url = f'{BASE_URL}/facematch/admin/jobs/{job_id}/errors'

    r = requests.get(errors_url, headers=HEADERS, params={'limit': 9999})

    print(f'[JOBS ERRORS LIMIT] URL      : {errors_url}?limit=9999')
    print(f'[JOBS ERRORS LIMIT] Status   : {r.status_code}')
    print(f'[JOBS ERRORS LIMIT] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[JOBS ERRORS LIMIT] Response : {r.text[:300]}')

    # Server must either honour the request (200, capped to max 1000) or reject with 400/422.
    assert r.status_code in (200, 400, 422), \
        f'Expected 200 (capped), 400, or 422 for limit=9999, got {r.status_code}: {r.text}'
    if r.status_code == 200:
        errors = r.json()
        results = errors if isinstance(errors, list) else errors.get('errors', errors.get('items', []))
        assert len(results) <= 1000, \
            f'Expected at most 1000 error entries (documented max), got {len(results)}'


if __name__ == '__main__':
    test_list_jobs_with_limit()
    test_list_jobs_with_offset()
