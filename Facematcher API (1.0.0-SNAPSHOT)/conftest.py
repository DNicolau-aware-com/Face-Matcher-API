# conftest.py — loaded by pytest before any test file
import sys, os, uuid
from datetime import datetime
import pytest

# 1. Add the project directory to sys.path so every test file can do
#    `from config import BASE_URL, HEADERS` without its own sys.path hack.
_project_dir = os.path.dirname(os.path.abspath(__file__))
if _project_dir not in sys.path:
    sys.path.insert(0, _project_dir)

# 2. Import pip's `requests` NOW (before any test file adds the local
#    `requests/` folder to sys.path) and pin it in sys.modules so it
#    is never replaced by the local namespace package.
import requests as _pip_requests  # noqa: E402
sys.modules['requests'] = _pip_requests

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
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
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
    import requests as _r
    r = _r.post(f'{base_url}/facematch/galleries', headers=headers, json={'name': name})
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

    import requests as _r
    _r.delete(f'{BASE_URL}/facematch/galleries/{name}', headers=HEADERS)
    shared_state.pop('gallery_name', None)
    print(f'\n[FIXTURE] session_gallery deleted: {name}')
