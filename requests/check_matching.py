import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import BASE_URL, HEADERS
from client.image_utils import encode_image

def check_verify(probe_path: str, reference_path: str, threshold: float = 4):
    r = requests.post(
        f"{BASE_URL}/facematch/verify",
        headers=HEADERS,
        json={
            "probe":     {"image": encode_image(probe_path)},
            "reference": {"image": encode_image(reference_path)},
            "threshold": threshold,
        },
    )
    print(f"[VERIFY] {r.status_code} -> {r.json()}")
    return r

def check_search(probe_path: str, gallery: str, max_candidates: int = 5, threshold: float = 4):
    r = requests.post(
        f"{BASE_URL}/facematch/search",
        headers=HEADERS,
        json={
            "probe":          {"image": encode_image(probe_path)},
            "gallery":        gallery,
            "max_candidates": max_candidates,
            "threshold":      threshold,
        },
    )
    print(f"[SEARCH] {r.status_code} -> {r.json()}")
    return r

if __name__ == "__main__":
    check_verify("assets/probe.jpg", "assets/reference.jpg")
    check_search("assets/probe.jpg", "employees")
