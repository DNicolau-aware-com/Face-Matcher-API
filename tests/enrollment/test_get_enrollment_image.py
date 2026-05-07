# -*- coding: utf-8 -*-
# GET /facematch/galleries/{galleryName}/enrollments/{identifier}/image
import uuid
import requests
import pytest
from config import BASE_URL, HEADERS, IMAGES

IMAGE_KEY          = 'dan_face'
NONEXISTENT_GALLERY = 'gallery_does_not_exist_xyz'
NONEXISTENT_ID      = 'identifier_does_not_exist_xyz'


def test_get_enrollment_image_returns_jpeg(session_gallery):
    # Enroll via single-image endpoint (which stores the image), then retrieve it.
    gallery = session_gallery
    ident   = f'img_test_{uuid.uuid4().hex[:8]}'
    image_b64 = IMAGES.get(IMAGE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{IMAGE_KEY}" not found in config. Check your .env file.')

    enroll_r = requests.post(
        f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ident}',
        headers=HEADERS,
        json={'image': image_b64},
    )
    assert enroll_r.status_code == 200, f'Pre-enroll failed: {enroll_r.status_code}: {enroll_r.text}'

    url = f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ident}/image'
    r   = requests.get(url, headers=HEADERS)

    print(f'[GET IMAGE] URL          : {url}')
    print(f'[GET IMAGE] Status       : {r.status_code}')
    print(f'[GET IMAGE] Content-Type : {r.headers.get("Content-Type", "not set")}')
    print(f'[GET IMAGE] Trace ID     : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[GET IMAGE] Body bytes   : {len(r.content)}')

    requests.delete(
        f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ident}',
        headers=HEADERS,
    )

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'
    assert 'image/jpeg' in r.headers.get('Content-Type', ''), \
        f'Expected image/jpeg Content-Type, got: {r.headers.get("Content-Type")}'
    assert len(r.content) > 0, 'Image response body is empty'


def test_get_enrollment_image_404_nonexistent_identifier():
    # Non-existent gallery/identifier must return 404.
    url = f'{BASE_URL}/facematch/galleries/{NONEXISTENT_GALLERY}/enrollments/{NONEXISTENT_ID}/image'
    r   = requests.get(url, headers=HEADERS)

    print(f'[GET IMAGE 404] URL    : {url}')
    print(f'[GET IMAGE 404] Status : {r.status_code}')
    print(f'[GET IMAGE 404] Body   : {r.text}')

    assert r.status_code == 404, f'Expected 404, got {r.status_code}: {r.text}'


def test_get_enrollment_image_404_when_not_stored(session_gallery):
    # Enroll via batch-images with storeImages=False — image should NOT be retrievable.
    gallery   = session_gallery
    ident     = f'no_img_{uuid.uuid4().hex[:8]}'
    image_b64 = IMAGES.get(IMAGE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{IMAGE_KEY}" not found in config. Check your .env file.')

    enroll_r = requests.post(
        f'{BASE_URL}/facematch/admin/enroll/batch-images',
        headers=HEADERS,
        json={
            'items':       [{'identifier': ident, 'image': image_b64}],
            'gallery':     gallery,
            'storeImages': False,
        },
    )
    assert enroll_r.status_code == 200, f'Pre-enroll failed: {enroll_r.status_code}: {enroll_r.text}'

    url = f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ident}/image'
    r   = requests.get(url, headers=HEADERS)

    print(f'[GET IMAGE NO STORE] URL    : {url}')
    print(f'[GET IMAGE NO STORE] Status : {r.status_code}')
    print(f'[GET IMAGE NO STORE] Body   : {r.text}')

    requests.delete(
        f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ident}',
        headers=HEADERS,
    )

    assert r.status_code == 404, f'Expected 404 (image not stored), got {r.status_code}: {r.text}'


def test_get_enrollment_image_200_when_stored_via_batch(session_gallery):
    # Enroll via batch-images with storeImages=True — image MUST be retrievable.
    gallery   = session_gallery
    ident     = f'store_img_{uuid.uuid4().hex[:8]}'
    image_b64 = IMAGES.get(IMAGE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{IMAGE_KEY}" not found in config. Check your .env file.')

    enroll_r = requests.post(
        f'{BASE_URL}/facematch/admin/enroll/batch-images',
        headers=HEADERS,
        json={
            'items':       [{'identifier': ident, 'image': image_b64}],
            'gallery':     gallery,
            'storeImages': True,
        },
    )
    assert enroll_r.status_code == 200, f'Pre-enroll failed: {enroll_r.status_code}: {enroll_r.text}'

    url = f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ident}/image'
    r   = requests.get(url, headers=HEADERS)

    print(f'[GET IMAGE STORED] URL          : {url}')
    print(f'[GET IMAGE STORED] Status       : {r.status_code}')
    print(f'[GET IMAGE STORED] Content-Type : {r.headers.get("Content-Type", "not set")}')
    print(f'[GET IMAGE STORED] Body bytes   : {len(r.content)}')

    requests.delete(
        f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ident}',
        headers=HEADERS,
    )

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'
    assert 'image/jpeg' in r.headers.get('Content-Type', ''), \
        f'Expected image/jpeg Content-Type, got: {r.headers.get("Content-Type")}'
    assert len(r.content) > 0, 'Image response body is empty'


if __name__ == '__main__':
    test_get_enrollment_image_404_nonexistent_identifier()
