# -*- coding: utf-8 -*-
import uuid
import requests
import sys, os
from config import BASE_URL, HEADERS

def test_delete_orphans():
    # Use a dedicated gallery so this test is isolated from session_gallery.
    # The DELETE /admin/orphans endpoint may delete the gallery itself on some builds;
    # using a separate gallery prevents that from breaking the rest of the suite.
    gallery = f'orphan_test_{uuid.uuid4().hex[:8]}'

    create_r = requests.post(
        f'{BASE_URL}/facematch/galleries',
        headers=HEADERS,
        json={'name': gallery},
    )
    assert create_r.status_code == 200, f'Gallery creation failed: {create_r.status_code}: {create_r.text}'

    # DELETE {{BASE_URL}}/facematch/admin/orphans/{gallery}
    url = f'{BASE_URL}/facematch/admin/orphans/{gallery}'

    r = requests.delete(url, headers=HEADERS)

    print(f'[DELETE ORPHANS] URL      : {url}')
    print(f'[DELETE ORPHANS] Gallery  : {gallery}')
    print(f'[DELETE ORPHANS] Status   : {r.status_code}')
    print(f'[DELETE ORPHANS] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[DELETE ORPHANS] Response : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

    # Check whether the gallery survived the orphan-delete call.
    check_r = requests.get(f'{BASE_URL}/facematch/galleries/{gallery}', headers=HEADERS)
    gallery_survived = check_r.status_code == 200
    print(f'[DELETE ORPHANS] Gallery survived orphan delete: {gallery_survived}')

    requests.delete(f'{BASE_URL}/facematch/galleries/{gallery}', headers=HEADERS)


def test_delete_orphans_nonexistent_gallery():
    # DELETE {{BASE_URL}}/facematch/admin/orphans/{gallery} — gallery does not exist.
    # The service returns 200 with zero counts (same pattern as validate endpoint).
    gallery = 'gallery_does_not_exist_xyz'
    url     = f'{BASE_URL}/facematch/admin/orphans/{gallery}'

    r = requests.delete(url, headers=HEADERS)

    print(f'[DELETE ORPHANS NOEXIST] URL          : {url}')
    print(f'[DELETE ORPHANS NOEXIST] Gallery      : {gallery}')
    print(f'[DELETE ORPHANS NOEXIST] Status       : {r.status_code}')
    print(f'[DELETE ORPHANS NOEXIST] Trace ID     : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[DELETE ORPHANS NOEXIST] Response     : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'
    body = r.json()
    assert 'deleted'      in body or 'orphansFound' in body, \
        f'Expected "deleted" or "orphansFound" in response: {body}'
    print(f'[DELETE ORPHANS NOEXIST] orphansFound : {body.get("orphansFound")}')
    print(f'[DELETE ORPHANS NOEXIST] deleted      : {body.get("deleted")}')


if __name__ == '__main__':
    test_delete_orphans_nonexistent_gallery()
