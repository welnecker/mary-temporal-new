from __future__ import annotations

import re
from typing import Dict, Optional


# ============================================================
# IDENTIDADE FIXA DA MARY
# ============================================================

MARY_IDENTITY_BLOCK = """
Mary, young adult woman, 24 years old, 1.68m height, 65kg,
smooth white skin, voluptuous feminine body, flat stomach,
wide hips, large and firm butt, thick thighs, medium breasts,
long black hair, expressive green eyes, sensual and confident presence.
""".strip()


# ============================================================
# ESTILO VISUAL FIXO
# ============================================================

STYLE_BLOCK = """
Adult comic book style, expressive American graphic novel style,
cinematic composition, dramatic shadows, rich contrast,
detailed ink lines, high detail, realistic anatomy,
stylized realism, professional illustration quality.
""".strip()


# ============================================================
# NEGATIVE BASE
# ============================================================

NEGATIVE_BASE = """
low quality, bad anatomy, deformed face, extra limbs, extra fingers,
blurry, distorted body, poorly drawn hands, childish cartoon style,
anime style, text artifacts, watermark, duplicated body parts,
cropped face, broken eyes, malformed hands, bad proportions
""".strip()


# ============================================================
# HELPERS
# ============================================================

def _clean_text(text: str) -> str:
    t = str(text or "").strip()
    if not t:
        return ""
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _norm_emotion(emotion: str) -> str:
    e = _clean_text(emotion).lower()

    if any(k in e for k in ["provoc", "sensual", "sedut", "atrevid", "quente"]):
        return "provocante"

    if any(k in e for k in ["tens", "nerv", "perig", "suspeit", "ansios"]):
        return "tensa"

    if any(k in e for k in ["íntim", "intim", "românt", "romant", "carinh", "delicad"]):
        return "intima"

    if any(k in e for k in ["domin", "segur", "confian", "poder", "controle"]):
        return "dominante"

    if any(k in e for k in ["trist", "melanc", "frág", "frag", "emocion"]):
        return "melancolica"

    if any(k in e for k in ["silenc", "fria", "neutra", "observ"]):
        return "silenciosa"

    return "neutra"


def _build_scene_block(
    *,
    scene_summary: str,
    local: str = "",
    roupa_mary: str = "",
    acao: str = "",
) -> str:
    parts = []

    if scene_summary:
        parts.append(f"Scene: {_clean_text(scene_summary)}")

    if local:
        parts.append(f"Location: {_clean_text(local)}")

    if roupa_mary:
        parts.append(f"Mary outfit: {_clean_text(roupa_mary)}")

    if acao:
        parts.append(f"Action focus: {_clean_text(acao)}")

    return "\n".join(parts).strip()


def _build_pose_block(*, emotion_key: str, acao: str = "") -> str:
    acao_clean = _clean_text(acao).lower()

    if "andar" in acao_clean or "saída" in acao_clean or "saida" in acao_clean:
        base_action = "Mary walking naturally, body in motion, with subtle expressive posture"
    elif "sent" in acao_clean:
        base_action = "Mary seated with elegant posture, body language expressive and intentional"
    elif "olh" in acao_clean:
        base_action = "Mary turning slightly, looking with expressive eyes and controlled body language"
    else:
        base_action = "Mary posed naturally, with expressive posture and visual presence"

    by_emotion = {
        "provocante": (
            "Mary slightly turning her body, looking over her shoulder, "
            "confident stance, subtle sensual tension in posture, relaxed but inviting expression."
        ),
        "tensa": (
            "Mary with guarded posture, subtle tension in shoulders and gaze, "
            "body slightly alert, expression controlled, emotionally charged stillness."
        ),
        "intima": (
            "Mary with soft body language, close and emotionally open posture, "
            "gentle expression, natural sensuality, subtle warmth in her gaze."
        ),
        "dominante": (
            "Mary standing with strong posture, chin slightly raised, confident presence, "
            "controlled expression, stable stance, visually commanding energy."
        ),
        "melancolica": (
            "Mary with softer posture, expressive eyes, emotionally reflective presence, "
            "subtle stillness, inward mood, elegant vulnerability."
        ),
        "silenciosa": (
            "Mary composed and observant, restrained expression, quiet body language, "
            "subtle emotional tension beneath calm posture."
        ),
        "neutra": (
            "Mary in a natural pose, expressive but balanced posture, "
            "visually grounded and believable body language."
        ),
    }

    pose = by_emotion.get(emotion_key, by_emotion["neutra"])
    return f"{base_action}\nPose and body language: {pose}"


def _build_camera_block(*, emotion_key: str) -> str:
    by_emotion = {
        "provocante": "Camera framing: medium-close shot, slightly low angle, emphasizing expression and body line.",
        "tensa": "Camera framing: medium shot, over-the-shoulder or slightly off-center framing, cinematic tension.",
        "intima": "Camera framing: close framing, soft medium-close shot, intimate visual distance.",
        "dominante": "Camera framing: medium shot, slightly low angle, clear visual authority and presence.",
        "melancolica": "Camera framing: medium-close shot, soft frontal composition, expressive face emphasis.",
        "silenciosa": "Camera framing: medium shot, still composition, restrained cinematic framing.",
        "neutra": "Camera framing: medium shot, balanced composition, clear subject focus.",
    }
    return by_emotion.get(emotion_key, by_emotion["neutra"])


def _build_lighting_block(*, emotion_key: str) -> str:
    by_emotion = {
        "provocante": (
            "Lighting: warm side lighting, soft shadows, subtle highlights on face and body contours, cinematic sensual mood."
        ),
        "tensa": (
            "Lighting: harder contrast, dramatic shadows, directional light, emotionally charged atmosphere."
        ),
        "intima": (
            "Lighting: low warm light, soft shadows, gentle contrast, intimate cinematic tone."
        ),
        "dominante": (
            "Lighting: defined contrast, sculpted highlights, strong visual separation, confident dramatic mood."
        ),
        "melancolica": (
            "Lighting: subdued soft light, emotional shadows, muted dramatic tone, reflective atmosphere."
        ),
        "silenciosa": (
            "Lighting: restrained warm-neutral light, quiet cinematic shadows, controlled atmosphere."
        ),
        "neutra": (
            "Lighting: cinematic warm lighting, balanced highlights and shadows, grounded realism."
        ),
    }
    return by_emotion.get(emotion_key, by_emotion["neutra"])


def _build_consistency_block() -> str:
    return (
        "Keep Mary's face visually consistent across generations, same green eyes, "
        "same facial structure, same long black hair, same body proportions, "
        "same adult American comic style, same visual identity, grounded realism."
    )


def _build_extra_block(extra: str) -> str:
    extra = _clean_text(extra)
    if not extra:
        return ""
    return f"Additional visual details: {extra}"


# ============================================================
# API PRINCIPAL
# ============================================================

def extract_visual_scene_summary(
    *,
    last_reply: str = "",
    local: str = "",
    roupa_mary: str = "",
    emocao: str = "",
    acao: str = "",
) -> str:
    parts = []

    acao_clean = _clean_text(acao)
    local_clean = _clean_text(local)
    roupa_clean = _clean_text(roupa_mary)
    emocao_clean = _clean_text(emocao)
    reply_clean = _clean_text(last_reply)

    if acao_clean:
        parts.append(acao_clean)

    if local_clean:
        parts.append(f"in {local_clean}")

    if roupa_clean:
        parts.append(f"wearing {roupa_clean}")

    if emocao_clean:
        parts.append(f"with a {emocao_clean} emotional tone")

    if reply_clean:
        parts.append(f"scene mood inspired by: {reply_clean[:220]}")

    return ", ".join([p for p in parts if p]).strip(", ")


def build_visual_prompt(
    *,
    scene_summary: str,
    local: str = "",
    roupa_mary: str = "",
    emocao: str = "",
    acao: str = "",
    extra: str = "",
) -> str:
    emotion_key = _norm_emotion(emocao)

    blocks = [
        STYLE_BLOCK,
        MARY_IDENTITY_BLOCK,
        _build_scene_block(
            scene_summary=scene_summary,
            local=local,
            roupa_mary=roupa_mary,
            acao=acao,
        ),
        _build_pose_block(
            emotion_key=emotion_key,
            acao=acao,
        ),
        _build_camera_block(emotion_key=emotion_key),
        _build_lighting_block(emotion_key=emotion_key),
    ]

    extra_block = _build_extra_block(extra)
    if extra_block:
        blocks.append(extra_block)

    blocks.append(_build_consistency_block())

    return "\n\n".join([b for b in blocks if b.strip()])


def build_negative_prompt(extra_negative: Optional[str] = None) -> str:
    extra_negative = _clean_text(extra_negative or "")
    if extra_negative:
        return f"{NEGATIVE_BASE}, {extra_negative}"
    return NEGATIVE_BASE


def build_prompt_from_scene_context(ctx: Dict[str, str]) -> Dict[str, str]:
    last_reply = ctx.get("last_reply", "")
    local = ctx.get("local", "")
    roupa_mary = ctx.get("roupa_mary", "")
    emocao = ctx.get("emocao", "")
    acao = ctx.get("acao", "")
    extra = ctx.get("extra", "")
    extra_negative = ctx.get("extra_negative", "")

    scene_summary = extract_visual_scene_summary(
        last_reply=last_reply,
        local=local,
        roupa_mary=roupa_mary,
        emocao=emocao,
        acao=acao,
    )

    prompt = build_visual_prompt(
        scene_summary=scene_summary,
        local=local,
        roupa_mary=roupa_mary,
        emocao=emocao,
        acao=acao,
        extra=extra,
    )

    negative_prompt = build_negative_prompt(extra_negative)

    return {
        "scene_summary": scene_summary,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
    }
