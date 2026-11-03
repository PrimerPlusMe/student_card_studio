"""Fetch a public-domain NASA face image for optional model acceptance tests.

This is a development/CI operation. The desktop application never downloads
images or sends student records to a network service.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from urllib.request import urlopen

URL = "https://raw.githubusercontent.com/scikit-image/scikit-image/v0.20.0/skimage/data/astronaut.png"
SHA256 = "88431cd9653ccd539741b555fb0a46b61558b301d4110412b5bc28b5e3ea6cb5"
DESTINATION = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "astronaut.png"


def main():
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    if not DESTINATION.is_file():
        with urlopen(URL, timeout=60) as response:
            data = response.read(2 * 1024 * 1024)
        if hashlib.sha256(data).hexdigest() != SHA256:
            raise RuntimeError("NASA fixture checksum did not match the pinned scikit-image image")
        DESTINATION.write_bytes(data)
    digest = hashlib.sha256(DESTINATION.read_bytes()).hexdigest()
    if digest != SHA256:
        raise RuntimeError("Existing NASA fixture checksum is not the pinned image")
    print(f"Fixture: {DESTINATION.name}; sha256={digest}")


if __name__ == "__main__":
    main()
