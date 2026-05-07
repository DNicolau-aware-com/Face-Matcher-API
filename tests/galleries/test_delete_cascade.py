# -*- coding: utf-8 -*-
# Verify that deleting a gallery removes all its enrollments.
import uuid
import requests
import pytest
from config import BASE_URL, HEADERS, IMAGES

IMAGE_KEY = 'dan_face'


def test_delete_gallery_removes_enrollments():
    # Create an isolated gallery, enroll a face, delete the gallery,
    # then verify the enrollment is no longer accessible.
    gallery_name = f'cascade_test_{uuid.uuid4().hex[:8]}'
    ident        = f'cascade_enroll_{uuid.uuid4().hex[:8]}'
    image_b64    = IMAGES.get(IMAGE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{IMAGE_KEY}" not found in config. Check your .env file.')

    # 1. Create gallery
    create_r = requests.post(
        f'{BASE_URL}/facematch/galleries',
        headers=HEADERS,
        json={'name': gallery_name},
    )
    assert create_r.status_code == 200, f'Gallery creation failed: {create_r.text}'
    print(f'[CASCADE] Gallery created : {gallery_name}')

    # 2. Enroll a face
    enroll_r = requests.post(
        f'{BASE_URL}/facematch/galleries/{gallery_name}/enrollments/{ident}',
        headers=HEADERS,
        json={'image': image_b64},
    )
    assert enroll_r.status_code == 200, f'Enroll failed: {enroll_r.status_code}: {enroll_r.text}'
    print(f'[CASCADE] Enrolled        : {ident}')

    # 3. Delete the gallery
    delete_r = requests.delete(
        f'{BASE_URL}/facematch/galleries/{gallery_name}',
        headers=HEADERS,
    )
    assert delete_r.status_code == 204, f'Gallery delete failed: {delete_r.status_code}: {delete_r.text}'
    print(f'[CASCADE] Gallery deleted : {gallery_name}')

    # 4. Attempting to delete the enrollment must now return 404 (gallery is gone)
    check_r = requests.delete(
        f'{BASE_URL}/facematch/galleries/{gallery_name}/enrollments/{ident}',
        headers=HEADERS,
    )
    print(f'[CASCADE] Post-delete enrollment delete status : {check_r.status_code}')
    assert check_r.status_code == 404, \
        f'Expected 404 after gallery deletion, got {check_r.status_code}: {check_r.text}'


if __name__ == '__main__':
    test_delete_gallery_removes_enrollments()
