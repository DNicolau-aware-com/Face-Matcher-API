# conftest.py — loaded by pytest before any test file
import json
import uuid
from datetime import datetime
import requests as _requests
import pytest


# ---------------------------------------------------------------------------
# CENTRALIZED HTTP LOGGER
#
#   Attaches a response hook to every requests.Session for the duration of
#   each test. Logs method, URL, status, elapsed time, and full response body.
#
#   Output modes (controlled by HTTP_LOG env var or --http-log CLI option):
#     always  → print every request/response
#     failure → print only when the test fails  (default)
#     never   → disable entirely
#
#   Usage:
#     pytest -s                          # failure-only (default)
#     pytest -s --http-log=always        # every request
#     HTTP_LOG=always pytest -s          # same via env var
# ---------------------------------------------------------------------------

def pytest_addoption(parser):
    parser.addoption(
        '--http-log',
        default='failure',
        choices=['always', 'failure', 'never'],
        help='HTTP request/response logging: always | failure (default) | never',
    )


def _format_body(response):
    try:
        return json.dumps(response.json(), indent=2)
    except Exception:
        text = response.text
        return text[:500] + ('...' if len(text) > 500 else '')


@pytest.fixture(autouse=True)
def _http_logger(request):
    """
    Intercept every HTTP response made during this test via requests event hooks.
    Stores a log of all calls; prints on failure (or always, depending on --http-log).
    """
    mode = request.config.getoption('--http-log', default='failure')
    if mode == 'never':
        yield
        return

    log = []

    def _on_response(r, *args, **kwargs):
        elapsed_ms = r.elapsed.total_seconds() * 1000 if r.elapsed else 0
        entry = {
            'method':   r.request.method,
            'url':      r.request.url,
            'status':   r.status_code,
            'elapsed':  elapsed_ms,
            'trace_id': r.headers.get('x-aware-trace-id', ''),
            'body':     _format_body(r),
        }
        log.append(entry)
        if mode == 'always':
            _print_entry(entry)

    _original_send = _requests.Session.send

    def _patched_send(self, prepared, **kwargs):
        response = _original_send(self, prepared, **kwargs)
        _on_response(response)
        return response

    _requests.Session.send = _patched_send

    yield

    _requests.Session.send = _original_send

    if mode == 'failure' and hasattr(request.node, 'rep_call') and request.node.rep_call.failed:
        print(f'\n{"="*60}')
        print(f'  HTTP LOG — {request.node.name}')
        print(f'{"="*60}')
        for entry in log:
            _print_entry(entry)
        print(f'{"="*60}')


def _print_entry(entry):
    trace = f'  trace={entry["trace_id"]}' if entry['trace_id'] else ''
    print(f'\n  >> {entry["method"]} {entry["url"]}')
    print(f'  << {entry["status"]}  ({entry["elapsed"]:.0f}ms){trace}')
    for line in entry['body'].splitlines()[:20]:
        print(f'     {line}')
    if entry['body'].count('\n') > 20:
        print(f'     ... (truncated)')


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Expose test outcome on item.rep_call so _http_logger can check it."""
    outcome = yield
    rep = outcome.get_result()
    if rep.when == 'call':
        item.rep_call = rep

# ---------------------------------------------------------------------------
# SHARED STATE — pytest equivalent of Postman environment variables.
#
#   shared_state is a plain dict that lives for the entire test session.
#   Tests that CREATE resources store their returned IDs here.
#   Tests that CONSUME those resources read from here first, then fall back
#   to the static values defined in their own file or in config.py.
#
#   Usage in a test file:
#
#       def test_create_gallery(shared_state):
#           ...
#           shared_state['gallery_name'] = r.json()['name']   # capture
#
#       def test_enroll(shared_state):
#           gallery = shared_state.get('gallery_name', GALLERY_NAME)  # consume
# ---------------------------------------------------------------------------

@pytest.fixture(scope='session')
def shared_state():
    """Session-scoped dict for passing captured values between tests."""
    return {}


# ---------------------------------------------------------------------------
# DYNAMIC VALUE FIXTURES — pytest equivalent of Postman {{$guid}} / {{$timestamp}}
#
#   unique_gallery_name  → e.g. "gallery_20250306_142305"  (stable per session)
#   unique_identifier    → e.g. "enroll_a3f1b2c4"          (stable per session)
#   random_uuid          → a fresh UUID string each time it is requested
# ---------------------------------------------------------------------------

@pytest.fixture(scope='session')
def unique_gallery_name():
    """Auto-generated gallery name, unique per test session."""
    ts   = datetime.now().strftime('%Y%m%d_%H%M%S')
    name = f'gallery_{ts}'
    print(f'\n[FIXTURE] unique_gallery_name = {name}')
    return name


@pytest.fixture(scope='session')
def unique_identifier():
    """Auto-generated enrollment identifier, unique per test session."""
    ident = f'enroll_{uuid.uuid4().hex[:8]}'
    print(f'\n[FIXTURE] unique_identifier = {ident}')
    return ident


@pytest.fixture
def random_uuid():
    """Fresh UUID string — new value every time the fixture is used."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# SESSION GALLERY — one auto-generated gallery shared across the entire run.
#
#   Creates the gallery ONCE (when first requested by any test), stores its
#   name in shared_state['gallery_name'], and deletes it at session teardown.
#
#   Tests that specifically test gallery CRUD (create/delete gallery) should
#   use the random_uuid fixture to generate their own isolated gallery name so
#   they don't conflict with the shared session gallery.
#
#   Usage:
#       def test_enroll(session_gallery, shared_state):
#           url = f'{BASE_URL}/facematch/galleries/{session_gallery}/enrollments/...'
# ---------------------------------------------------------------------------

def _ensure_gallery(name, base_url, headers):
    """
    Create a gallery if it does not already exist.

    - 200 → gallery was just created
    - 400 (Gallery Exists) → gallery already exists, proceed
    - anything else → raises RuntimeError

    Returns the gallery name so callers can do: gallery = _ensure_gallery(...)
    """
    import requests
    r = requests.post(f'{base_url}/facematch/galleries', headers=headers, json={'name': name})
    if r.status_code == 200:
        print(f'\n[ensure_gallery] Created: {name}')
    elif r.status_code == 400:
        print(f'\n[ensure_gallery] Already exists, reusing: {name}')
    else:
        raise RuntimeError(f'[ensure_gallery] Unexpected status {r.status_code} for "{name}": {r.text}')
    return name


@pytest.fixture(scope='session')
def session_gallery(shared_state):
    """
    Auto-generates a unique gallery name once per session, ensures it exists
    (creates it if not), stores the name in shared_state['gallery_name'], and
    deletes it on teardown.

    All tests that enroll, search, or verify against a gallery should declare
    this fixture — they all receive the same gallery name for the run.

    Tests that specifically test gallery CRUD should use random_uuid instead to
    generate their own isolated name (gallery_create_test key in shared_state).
    """
    from config import BASE_URL, HEADERS

    ts   = datetime.now().strftime('%Y%m%d_%H%M%S')
    name = f'gallery_{ts}'

    _ensure_gallery(name, BASE_URL, HEADERS)

    shared_state['gallery_name'] = name
    print(f'\n[FIXTURE] session_gallery ready: {name}')

    yield name

    import requests
    requests.delete(f'{BASE_URL}/facematch/galleries/{name}', headers=HEADERS)
    shared_state.pop('gallery_name', None)
    print(f'\n[FIXTURE] session_gallery deleted: {name}')
