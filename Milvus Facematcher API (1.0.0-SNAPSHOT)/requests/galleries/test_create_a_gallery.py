# -*- coding: utf-8 -*-
import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS

def test_create_a_gallery(shared_state, random_uuid):
    # PRE-REQUEST: generate a unique gallery name just for this test using random_uuid.
    # This is isolated from session_gallery to avoid conflicts when running the full suite.
    gallery = f'gallery_{random_uuid[:8]}'

    # POST {{BASE_URL}}/facematch/galleries
    url     = f'{BASE_URL}/facematch/galleries'
    payload = {'name': gallery}

    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[CREATE GALLERY] URL        : {url}')
    print(f'[CREATE GALLERY] Payload    : {payload}')
    print(f'[CREATE GALLERY] Status     : {r.status_code}')
    print(f'[CREATE GALLERY] Trace ID   : {r.headers.get("x-aware-trace-id", "not returned")}')

    if r.status_code == 200:
        body = r.json()
        print(f'[CREATE GALLERY] Name       : {body.get("name")}')
        print(f'[CREATE GALLERY] Created At : {body.get("createdAt")}')
        print(f'[CREATE GALLERY] Face Count : {body.get("faceCount")}')

        # Store under a gallery-test-specific key so it doesn't overwrite session_gallery
        shared_state['gallery_create_test'] = body.get('name', gallery)
        print(f'[CREATE GALLERY] >> shared_state["gallery_create_test"] = {shared_state["gallery_create_test"]}')
    elif r.status_code == 400:
        body = r.json()
        print(f'[CREATE GALLERY] Error      : {body.get("error")}')
        print(f'[CREATE GALLERY] Message    : {body.get("message")}')
    else:
        print(f'[CREATE GALLERY] Response   : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'