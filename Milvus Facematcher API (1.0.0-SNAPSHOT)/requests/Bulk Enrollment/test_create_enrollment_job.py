# -*- coding: utf-8 -*-
import requests
import pytest
import re
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, IMAGES

ENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..', '.env'))

def _save_job_id_to_env(job_id):
    with open(ENV_PATH, 'r', encoding='utf-8-sig') as f:
        content = f.read()
    if re.search(r'^JOB_ID=', content, re.MULTILINE):
        content = re.sub(r'^JOB_ID=.*', f'JOB_ID={job_id}', content, flags=re.MULTILINE)
    else:
        content += f'\nJOB_ID={job_id}\n'
    with open(ENV_PATH, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'[CREATE JOB] JOB_ID saved to .env: {job_id}')

def test_create_enrollment_job(session_gallery, shared_state):
    # PRE-REQUEST: use session_gallery so the gallery always exists (created or reused).
    gallery = session_gallery

    # POST {{BASE_URL}}/facematch/admin/jobs
    url = f'{BASE_URL}/facematch/admin/jobs'

    dan_image  = IMAGES.get('dan_face')
    john_image = IMAGES.get('john_face')
    part_face  = IMAGES.get('part_face')

    if not dan_image:
        print('[CREATE JOB] ERROR: IMAGE_DAN_FACE not found in config. Check your .env file.')
        pytest.fail("Image not found in config. Check your .env file.")
    if not john_image:
        print('[CREATE JOB] ERROR: IMAGE_JOHN_FACE not found in config. Check your .env file.')
        pytest.fail("Image not found in config. Check your .env file.")
    if not part_face:
        print('[CREATE JOB] ERROR: IMAGE_PART_FACE not found in config. Check your .env file.')
        pytest.fail("Image not found in config. Check your .env file.")

    payload = {
        'items': [
            {'identifier': 'dan_face',  'image': dan_image},
            {'identifier': 'john_face', 'image': john_image},
            {'identifier': 'part_face', 'image': part_face},
        ],
        'gallery': gallery,
    }

    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[CREATE JOB] URL      : {url}')
    print(f'[CREATE JOB] Gallery  : {gallery}')
    print(f'[CREATE JOB] Items    : {len(payload["items"])}')
    print(f'[CREATE JOB] Status   : {r.status_code}')
    print(f'[CREATE JOB] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[CREATE JOB] Response : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

    job_id = r.json().get('jobId')
    if job_id:
        _save_job_id_to_env(job_id)
        # TEST SCRIPT: also store in shared_state so test_delete_job can use it immediately
        shared_state['job_id'] = job_id
        print(f'[CREATE JOB] >> shared_state["job_id"] = {job_id}')
    else:
        print('[CREATE JOB] WARNING: jobId not found in response, .env not updated.')

if __name__ == '__main__':
    test_create_enrollment_job()
