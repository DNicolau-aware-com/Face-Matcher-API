# -*- coding: utf-8 -*-
# Request tracing — x-aware-trace-id header behavior.
import uuid
import requests
import pytest
from config import BASE_URL, HEADERS

TRACE_HEADER = 'x-aware-trace-id'


def test_trace_id_custom_echoed_back():
    # A custom x-aware-trace-id sent in the request must be returned unchanged in the response.
    custom_id = f'test-trace-{uuid.uuid4()}'
    headers   = {**HEADERS, TRACE_HEADER: custom_id}

    r = requests.get(f'{BASE_URL}/facematch/health', headers=headers)

    print(f'[TRACE CUSTOM] Sent     : {custom_id}')
    print(f'[TRACE CUSTOM] Received : {r.headers.get(TRACE_HEADER, "absent")}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'
    returned = r.headers.get(TRACE_HEADER)
    assert returned == custom_id, \
        f'Expected trace ID "{custom_id}" echoed back, got "{returned}"'


def test_trace_id_auto_generated_when_omitted():
    # When x-aware-trace-id is omitted the server must auto-generate a UUID and return it.
    headers = {k: v for k, v in HEADERS.items() if k.lower() != TRACE_HEADER}

    r = requests.get(f'{BASE_URL}/facematch/health', headers=headers)

    trace_id = r.headers.get(TRACE_HEADER)
    print(f'[TRACE AUTO] Status   : {r.status_code}')
    print(f'[TRACE AUTO] Received : {trace_id}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'
    assert trace_id, f'Expected {TRACE_HEADER} header in response, but it was absent'

    try:
        uuid.UUID(trace_id)
    except ValueError:
        pytest.fail(f'Expected auto-generated trace ID to be a UUID, got: "{trace_id}"')


def test_trace_id_present_on_all_endpoints():
    # The trace ID header must be returned on every major endpoint.
    endpoints = [
        ('GET',  f'{BASE_URL}/facematch/version'),
        ('GET',  f'{BASE_URL}/facematch/health'),
        ('GET',  f'{BASE_URL}/facematch/galleries'),
        ('GET',  f'{BASE_URL}/facematch/admin/queue'),
    ]
    for method, url in endpoints:
        r = requests.request(method, url, headers=HEADERS)
        assert TRACE_HEADER in r.headers, \
            f'Missing {TRACE_HEADER} header on {method} {url} (status {r.status_code})'
        print(f'[TRACE PRESENT] {method} {url} → {r.headers[TRACE_HEADER]}')


if __name__ == '__main__':
    test_trace_id_custom_echoed_back()
    test_trace_id_auto_generated_when_omitted()
    test_trace_id_present_on_all_endpoints()
