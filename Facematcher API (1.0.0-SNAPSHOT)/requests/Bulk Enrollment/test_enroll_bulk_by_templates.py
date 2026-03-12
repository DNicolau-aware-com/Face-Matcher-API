# -*- coding: utf-8 -*-
import requests
import pytest
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, IMAGES

# POST /facematch/admin/enroll/bulk
# Batch enroll with pre-extracted templates (admin, no SDK calls).
# Requires templates — we obtain them first via POST /facematch/admin/export/batch,
# then use the returned base64 templates as input to /enroll/bulk.

def _export_templates(images: dict) -> dict:
    """Export templates for a dict of {identifier: b64_image}. Returns {identifier: template}."""
    url = f'{BASE_URL}/facematch/admin/export/batch'
    payload = {
        'images': [{'identifier': k, 'image': v} for k, v in images.items()]
    }
    r = requests.post(url, headers=HEADERS, json=payload)
    assert r.status_code == 200, f'[EXPORT BATCH] Failed to export templates: {r.status_code} {r.text}'
    results = r.json().get('results', [])
    return {item['identifier']: item['template'] for item in results if item.get('success')}


def test_enroll_bulk_by_templates(session_gallery):
    # PRE-REQUEST: session_gallery ensures the gallery exists.
    gallery   = session_gallery
    dan_image  = IMAGES.get('dan_face')
    john_image = IMAGES.get('john_face')

    if not dan_image:
        pytest.fail('[ENROLL BULK TEMPLATES] IMAGE_DAN_FACE not found in config. Check your .env file.')
    if not john_image:
        pytest.fail('[ENROLL BULK TEMPLATES] IMAGE_JOHN_FACE not found in config. Check your .env file.')

    # Step 1 — export templates
    raw_images = {'bulk_tmpl_dan': dan_image, 'bulk_tmpl_john': john_image}
    templates  = _export_templates(raw_images)

    assert len(templates) == 2, \
        f'[ENROLL BULK TEMPLATES] Expected 2 exported templates, got {len(templates)}'

    # Step 2 — enroll via /enroll/bulk
    url = f'{BASE_URL}/facematch/admin/enroll/bulk'
    payload = {
        'items': [
            {'identifier': ident, 'template': tmpl}
            for ident, tmpl in templates.items()
        ],
        'gallery': gallery,
    }

    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[ENROLL BULK TEMPLATES] URL      : {url}')
    print(f'[ENROLL BULK TEMPLATES] Gallery  : {gallery}')
    print(f'[ENROLL BULK TEMPLATES] Items    : {len(payload["items"])}')
    print(f'[ENROLL BULK TEMPLATES] Status   : {r.status_code}')
    print(f'[ENROLL BULK TEMPLATES] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[ENROLL BULK TEMPLATES] Response : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'


if __name__ == '__main__':
    test_enroll_bulk_by_templates()
