from __future__ import annotations

import streamlit as st

from core.repositories import get_facts
from core.image_prompt_builder import build_prompt_from_scene_context
from core.image_service import generate_image, image_data_url_to_bytes
from core.cloudinary_service import upload_image_bytes
from core.image_prompt_refiner import refine_visual_prompt


st.set_page_config(
    page_title="Mary Imagens",
    page_icon="🎬",
    layout="centered",
)

SENHA_CORRETA = "311071"


# ==========================================================
# UI
# ==========================================================
def _apply_dark_ui() -> None:
    st.markdown(
        """
        <style>
        html, body, #root, .stApp { background: #0b0b0b !important; }
        .block-container { max-width: 980px !important; padding-top: 1rem !important; }
        input, textarea { background: #101010 !important; color: #f2f2f2 !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def check_password() -> bool:
    if "senha_ok" not in st.session_state:
        st.session_state["senha_ok"] = False

    if st.session_state["senha_ok"]:
        return True

    st.title("🔐 Acesso Restrito")
    senha = st.text_input("Senha", type="password")

    if st.button("Entrar"):
        if senha == SENHA_CORRETA:
            st.session_state["senha_ok"] = True
            st.rerun()
        else:
            st.error("Senha incorreta")

    return False


# ==========================================================
# HELPERS
# ==========================================================
def _uid():
    return (st.session_state.get("user_id") or "Janio Donisete").strip()


def _timeline():
    return (st.session_state.get("mary_timeline") or "cumplice").strip()


def _usuario_key_atual():
    return f"{_uid()}::mary::{_timeline()}"


def cached_get_facts(usuario_key: str) -> dict:
    try:
        return get_facts(usuario_key) or {}
    except Exception:
        return {}


def _get_nested(data, path):
    cur = data
    for p in path.split("."):
        if not isinstance(cur, dict):
            return ""
        cur = cur.get(p)
    return cur or ""


def _get_current_visual_context():
    facts = cached_get_facts(_usuario_key_atual())

    return {
        "local": _get_nested(facts, "cena.local") or _get_nested(facts, "state.local"),
        "roupa_mary": _get_nested(facts, "state.roupa"),
        "acao": _get_nested(facts, "cena.acao") or _get_nested(facts, "state.assunto"),
        "emocao": st.session_state.get("visual_emotion", ""),
        "extra": st.session_state.get("visual_extra", ""),
        "extra_negative": st.session_state.get("visual_extra_negative", ""),
    }


def _init_state():
    defaults = {
        "visual_prompt": "",
        "visual_negative_prompt": "",
        "visual_scene_summary": "",
        "visual_manual_mode": False,
        "visual_last_image_bytes": None,
        "visual_last_prompt": "",
        "visual_last_negative_prompt": "",
        "visual_last_seed": "",
        "visual_last_cloudinary_url": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ==========================================================
# MAIN
# ==========================================================
def main():
    _apply_dark_ui()

    if not check_password():
        st.stop()

    _init_state()

    st.title("🎬 Mary Imagens")

    # ======================================================
    # CONTROLES
    # ======================================================
    st.toggle("✍️ Usar prompt manual", key="visual_manual_mode")

    c1, c2 = st.columns(2)

    # =========================
    # MONTAR PROMPT
    # =========================
    with c1:
        if st.button("🛠️ Montar prompt automático", use_container_width=True):

            if st.session_state["visual_manual_mode"]:
                st.warning("Modo manual ativo")
            else:
                ctx = _get_current_visual_context()
                built = build_prompt_from_scene_context(ctx)

                st.session_state["visual_prompt"] = built["prompt"]
                st.session_state["visual_negative_prompt"] = built["negative_prompt"]
                st.session_state["visual_scene_summary"] = built["scene_summary"]

                st.success("Prompt criado")
                st.rerun()

    # =========================
    # REFINAR PROMPT
    # =========================
    with c2:
        if st.button("✨ Refinar com IA", use_container_width=True):

            prompt = st.session_state["visual_prompt"]

            if not prompt:
                st.error("Sem prompt")
            else:
                try:
                    refined = refine_visual_prompt(
                        base_prompt=prompt,
                        scene_summary=st.session_state["visual_scene_summary"],
                        emotion=st.session_state.get("visual_emotion"),
                        extra=st.session_state.get("visual_extra"),
                    )

                    st.session_state["visual_prompt"] = refined
                    st.success("Refinado")
                    st.rerun()

                except Exception as e:
                    st.error(f"Erro: {e}")

    # ======================================================
    # CAMPOS
    # ======================================================
    st.text_input("Emoção", key="visual_emotion")
    st.text_area("Extras", key="visual_extra")
    st.text_area("Negativos", key="visual_extra_negative")

    st.text_area("Prompt", key="visual_prompt", height=250)
    st.text_area("Negative Prompt", key="visual_negative_prompt", height=120)

    # ======================================================
    # GERAR
    # ======================================================
    if st.button("🖼️ Gerar imagem"):

        prompt = st.session_state["visual_prompt"]
        neg = st.session_state["visual_negative_prompt"]

        if not prompt:
            st.error("Sem prompt")
            return

        try:
            result = generate_image(
                prompt=prompt,
                negative_prompt=neg,
                aspect_ratio="3:4",
                image_size="1K",
            )

            img_url = result["images"][0]["image_url"]["url"]
            img_bytes = image_data_url_to_bytes(img_url)

            st.session_state["visual_last_image_bytes"] = img_bytes
            st.session_state["visual_last_prompt"] = prompt

            # upload cloudinary
            up = upload_image_bytes(img_bytes=img_bytes, folder="mary")
            st.session_state["visual_last_cloudinary_url"] = up.get("secure_url", "")

        except Exception as e:
            st.error(str(e))

    # ======================================================
    # RESULTADO
    # ======================================================
    if st.session_state["visual_last_image_bytes"]:
        st.image(st.session_state["visual_last_image_bytes"])

        st.download_button(
            "💾 Baixar",
            st.session_state["visual_last_image_bytes"],
            file_name="mary.png",
        )

        if st.session_state["visual_last_cloudinary_url"]:
            st.code(st.session_state["visual_last_cloudinary_url"])


if __name__ == "__main__":
    main()
