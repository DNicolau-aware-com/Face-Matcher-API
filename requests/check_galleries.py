import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import BASE_URL, HEADERS

def check_list_galleries():
    r = requests.get(
        f"{BASE_URL}/facematch/galleries",
        headers=HEADERS,
        params={"page": 0, "size": 5, "sort": "createdAt,desc"},
    )
    print(f"[LIST GALLERIES] {r.status_code} -> {r.json()}")
    return r

def check_create_gallery(name: str):
    r = requests.post(
        f"{BASE_URL}/facematch/galleries",
        headers=HEADERS,
        json={"name": name},
    )
    print(f"[CREATE GALLERY] {r.status_code} -> {r.text or '(no body)'}")
    return r

def check_delete_gallery(name: str):
    r = requests.delete(
        f"{BASE_URL}/facematch/galleries/{name}",
        headers=HEADERS,
    )
    print(f"[DELETE GALLERY] {r.status_code} -> {r.text or '(no body)'}")
    return r

if __name__ == "__main__":
    check_create_gallery("test_gallery")
    check_list_galleries()
    check_delete_gallery("test_gallery")
