from __future__ import annotations

import base64
from typing import Any, Dict, Optional

import cloudinary
import cloudinary.uploader


# ==========================================================
# CONFIG FIXA (TEMPORÁRIA / TESTE LOCAL)
# ==========================================================
CLOUDINARY_CLOUD_NAME = "drupewp1y"
CLOUDINARY_API_KEY = "133845212134728"
CLOUDINARY_API_SECRET = "3biOYu17wxMikhrfTd0QJ65zvJI"


# ==========================================================
# CONFIG CLOUDINARY
# ==========================================================
def _ensure_cloudinary_config() -> None:
    cloud_name = str(CLOUDINARY_CLOUD_NAME or "").strip()
    api_key = str(CLOUDINARY_API_KEY or "").strip()
    api_secret = str(CLOUDINARY_API_SECRET or "").strip()

    if not cloud_name:
        raise RuntimeError("CLOUDINARY_CLOUD_NAME não encontrado.")
    if not api_key:
        raise RuntimeError("CLOUDINARY_API_KEY não encontrado.")
    if not api_secret:
        raise RuntimeError("CLOUDINARY_API_SECRET não encontrado.")

    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
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
    """
    Upload de imagem (bytes) para Cloudinary.
    Retorna payload completo do Cloudinary.
    """
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
