# -*- coding: utf-8 -*-
# Negative tests — 409 Conflict
import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, IMAGES

ENROLLMENT_ID = 'conflict_test_id'  # isolated identifier — cleaned up after test

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

def test_409_enroll_duplicate_identifier(session_gallery):
    # POST {{BASE_URL}}/facematch/galleries/{galleryName}/enrollments/{identifier}
    # Enroll the same identifier twice into session_gallery — second must return 409
    gallery      = session_gallery
    url          = f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ENROLLMENT_ID}'
    image_base64 = IMAGES.get('dan_face')

    if not image_base64:
        print('[409] ERROR: IMAGE_DAN_FACE not found in config. Check your .env file.')
        return

    payload = {'image': image_base64}

    # First enroll — 200 (new) or 409 (already exists from a previous run's cleanup failure)
    requests.post(url, headers=HEADERS, json=payload)

    # Second enroll of the same identifier must return 409
    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'\n[409] Enroll — duplicate identifier')
    print(f'  URL        : {url}')
    print(f'  Gallery    : {gallery}')
    print(f'  Identifier : {ENROLLMENT_ID}')
    print(f'  Status     : {r.status_code}')
    _assert_error_format(r, 409)

    # Cleanup: remove the test enrollment so it doesn't conflict with later enrollment tests
    requests.delete(url, headers=HEADERS)

if __name__ == '__main__':
    test_409_enroll_duplicate_identifier()
