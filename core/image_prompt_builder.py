from __future__ import annotations

import re
from typing import Dict, Optional


MARY_BASE = """
Mary, young adult woman, 24 years old, 1.68m height, 65kg, smooth white skin,
voluptuous body, flat stomach, wide hips, large and firm butt, thick thighs,
medium breasts, long black hair, expressive green eyes, sensual and confident presence.
""".strip()

STYLE_BASE = """
Adult comic book style, expressive American graphic novel style,
cinematic composition, dramatic shadows, rich contrast,
detailed ink lines, high detail, realistic anatomy,
stylized realism, professional illustration quality.
""".strip()

NEGATIVE_BASE = """
low quality, bad anatomy, deformed face, extra limbs, extra fingers,
blurry, distorted body, poorly drawn hands, childish cartoon style,
anime style, text artifacts, watermark
""".strip()


def _clean_text(text: str) -> str:
    t = str(text or "").strip()
    if not t:
        return ""
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def extract_visual_scene_summary(
    *,
    last_reply: str = "",
    local: str = "",
    roupa_mary: str = "",
    emocao: str = "",
    acao: str = "",
) -> str:
    parts = []

    if acao:
        parts.append(_clean_text(acao))

    if local:
        parts.append(f"in { _clean_text(local) }")

    if roupa_mary:
        parts.append(f"wearing { _clean_text(roupa_mary) }")

    if emocao:
        parts.append(f"with a { _clean_text(emocao) } emotional tone")

    last_reply_clean = _clean_text(last_reply)
    if last_reply_clean:
        parts.append(f"scene mood inspired by: {last_reply_clean[:220]}")

    return ", ".join([p for p in parts if p]).strip(", ")


def build_visual_prompt(
    *,
    scene_summary: str,
    local: str = "",
    roupa_mary: str = "",
    emocao: str = "",
    enquadramento: str = "medium shot",
    iluminacao: str = "cinematic warm lighting",
    extra: str = "",
) -> str:
    blocks = [
        STYLE_BASE,
        MARY_BASE,
        f"Scene: { _clean_text(scene_summary) }",
    ]

    if local.strip():
        blocks.append(f"Location: { _clean_text(local) }")
    if roupa_mary.strip():
        blocks.append(f"Mary outfit: { _clean_text(roupa_mary) }")
    if emocao.strip():
        blocks.append(f"Emotional atmosphere: { _clean_text(emocao) }")
    if enquadramento.strip():
        blocks.append(f"Camera framing: { _clean_text(enquadramento) }")
    if iluminacao.strip():
        blocks.append(f"Lighting: { _clean_text(iluminacao) }")
    if extra.strip():
        blocks.append(f"Additional visual details: { _clean_text(extra) }")

    blocks.append(
        "Keep Mary's face visually consistent, expressive green eyes, long black hair, "
        "voluptuous silhouette, adult American comic style, grounded realism."
    )

    return "\n".join(blocks)


def build_negative_prompt(extra_negative: Optional[str] = None) -> str:
    if extra_negative and str(extra_negative).strip():
        return f"{NEGATIVE_BASE}, {str(extra_negative).strip()}"
    return NEGATIVE_BASE


def build_prompt_from_scene_context(ctx: Dict[str, str]) -> Dict[str, str]:
    scene_summary = extract_visual_scene_summary(
        last_reply=ctx.get("last_reply", ""),
        local=ctx.get("local", ""),
        roupa_mary=ctx.get("roupa_mary", ""),
        emocao=ctx.get("emocao", ""),
        acao=ctx.get("acao", ""),
    )

    prompt = build_visual_prompt(
        scene_summary=scene_summary,
        local=ctx.get("local", ""),
        roupa_mary=ctx.get("roupa_mary", ""),
        emocao=ctx.get("emocao", ""),
        enquadramento=ctx.get("enquadramento", "medium shot"),
        iluminacao=ctx.get("iluminacao", "cinematic warm lighting"),
        extra=ctx.get("extra", ""),
    )

    negative_prompt = build_negative_prompt(ctx.get("extra_negative", ""))

    return {
        "scene_summary": scene_summary,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
    }
