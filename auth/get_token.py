# -*- coding: utf-8 -*-
import requests
import os
from dotenv import load_dotenv

# Load .env from AWRNSS-AUT root
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.abspath(os.path.join(BASE_DIR, '..', '.env'))
load_dotenv(ENV_PATH)

# TODO: update LOGIN_URL and field names once login endpoint is confirmed
LOGIN_URL = 'https://dev24.awareid.com/<login-endpoint>'
USERNAME  = os.getenv('USERNAME')
PASSWORD  = os.getenv('PASSWORD')

def get_token():
    payload = {
        '<username_field>': USERNAME,
        '<password_field>': PASSWORD,
    }

    print(f'[AUTH] Requesting token from : {LOGIN_URL}')
    r = requests.post(LOGIN_URL, json=payload)
    print(f'[AUTH] Status               : {r.status_code}')

    if r.status_code == 200:
        token = r.json().get('<token_field>')
        print(f'[AUTH] Token received       : {token[:20]}...')

        # Write token back to .env so all projects pick it up automatically
        _update_env_token(ENV_PATH, token)
        return token
    else:
        print(f'[AUTH] Failed               : {r.text}')
        return None

def _update_env_token(env_path: str, token: str):
    with open(env_path, 'r') as f:
        lines = f.readlines()

    updated = False
    for i, line in enumerate(lines):
        if line.startswith('TOKEN='):
            lines[i] = f'TOKEN={token}\n'
            updated = True
            break

    if not updated:
        lines.append(f'TOKEN={token}\n')

    with open(env_path, 'w') as f:
        f.writelines(lines)

    print(f'[AUTH] Token saved to .env  : {env_path}')

if __name__ == '__main__':
    get_token()