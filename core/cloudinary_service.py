from __future__ import annotations

import base64
import os
from typing import Any, Dict, Optional

import cloudinary
import cloudinary.uploader
import streamlit as st


def _get_secret(name: str) -> str:
    val = (
        st.secrets.get(name)
        or os.getenv(name)
        or ""
    )
    return str(val).strip()


def _ensure_cloudinary_config() -> None:
    cloud_name = _get_secret("CLOUDINARY_CLOUD_NAME")
    api_key = _get_secret("CLOUDINARY_API_KEY")
    api_secret = _get_secret("CLOUDINARY_API_SECRET")

    if not cloud_name or not api_key or not api_secret:
        raise RuntimeError(
            "Cloudinary não configurado. Defina CLOUDINARY_CLOUD_NAME, "
            "CLOUDINARY_API_KEY e CLOUDINARY_API_SECRET."
        )

    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True,
    )


def upload_image_bytes(
    *,
    img_bytes: bytes,
    folder: str = "mary",
    public_id: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """
    Faz upload de bytes PNG/JPG para Cloudinary e devolve o payload completo.
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
    return result
