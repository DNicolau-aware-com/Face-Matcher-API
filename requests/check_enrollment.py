import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import BASE_URL, HEADERS
from client.image_utils import encode_image

def check_enroll(gallery: str, enrollment_id: str, image_path: str):
    r = requests.post(
        f"{BASE_URL}/facematch/galleries/{gallery}/enrollments/{enrollment_id}",
        headers=HEADERS,
        json={"image": encode_image(image_path)},
    )
    print(f"[ENROLL] {r.status_code} -> {r.text or '(no body)'}")
    return r

def check_delete_enrollment(gallery: str, enrollment_id: str):
    r = requests.delete(
        f"{BASE_URL}/facematch/galleries/{gallery}/enrollments/{enrollment_id}",
        headers=HEADERS,
    )
    print(f"[DELETE ENROLLMENT] {r.status_code} -> {r.text or '(no body)'}")
    return r

if __name__ == "__main__":
    check_enroll("test_gallery", "face_001", "assets/face.jpg")
    check_delete_enrollment("test_gallery", "face_001")
