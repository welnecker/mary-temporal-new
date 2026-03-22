from __future__ import annotations

import base64
import os
from typing import Any, Dict, Optional

import cloudinary
import cloudinary.uploader


def _ensure_cloudinary_config() -> None:
    cloudinary.config(
        cloud_name="drupewp1y",
        api_key="133845212134728",
        api_secret="3biOYu17wxMikhrfTd0QJ65zvJI",
        secure=True,
    )


# ==========================================================
# UPLOAD
# ==========================================================
def upload_image_bytes(
    *,
    img_bytes: bytes,
    folder: str = "mary",
    public_id: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> Dict[str, Any]:
    _ensure_cloudinary_config()

    if not img_bytes:
        raise RuntimeError("img_bytes vazio para upload.")

    data_uri = "data:image/png;base64," + base64.b64encode(img_bytes).decode("utf-8")

    options: Dict[str, Any] = {
        "folder": folder,
        "resource_type": "image",
        "overwrite": False,
    }

    if public_id:
        options["public_id"] = public_id

    if tags:
        options["tags"] = tags

    result = cloudinary.uploader.upload(data_uri, **options)

    if not result or "secure_url" not in result:
        raise RuntimeError(f"Upload falhou. Resposta inesperada: {result}")

    return result
