from __future__ import annotations

import re
import streamlit as st

from core.repositories import get_facts
from core.image_prompt_builder import build_prompt_from_scene_context
from core.image_service import generate_image, image_data_url_to_bytes


st.set_page_config(
    page_title="Mary Imagens",
    page_icon="🎬",
    layout="centered",
)


SENHA_CORRETA = "311071"


def _apply_dark_ui() -> None:
    st.markdown(
        """
        <style>
        html, body, #root, .stApp { background: #0b0b0b !important; }
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stMainBlockContainer"] { background: #0b0b0b !important; }

        .block-container {
            max-width: 980px !important;
            padding-top: 1rem !important;
            padding-bottom: 4rem !important;
        }

        div[data-testid="stTextInput"] input,
        div[data-testid="stTextArea"] textarea,
        div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
            background: #101010 !important;
            color: #f2f2f2 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def check_password() -> bool:
    if "senha_ok" not in st.session_state:
        st.session_state["senha_ok"] = False

    if st.session_state["senha_ok"]:
        return True

    _apply_dark_ui()
    st.title("🔐 Acesso Restrito")

    with st.form("form_senha", clear_on_submit=False):
        senha = st.text_input("Digite a senha de acesso:", type="password")
        ok = st.form_submit_button("Entrar")

    if ok:
        if senha == SENHA_CORRETA:
            st.session_state["senha_ok"] = True
            st.success("Acesso liberado!")
            st.rerun()
        else:
            st.error("Senha incorreta.")

    return False


def _uid() -> str:
    uid = (st.session_state.get("user_id") or "Janio Donisete").strip()
    return uid or "Janio Donisete"


def _timeline() -> str:
    return str(st.session_state.get("mary_timeline") or "cumplice").strip() or "cumplice"


def _usuario_key_atual() -> str:
    return f"{_uid()}::mary::{_timeline()}"


def _get_nested_fact(data: dict, path: str, default=None):
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(part)
        if cur is None:
            return default
    return cur


def cached_get_facts(usuario_key: str) -> dict:
    try:
        data = get_facts(usuario_key) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _get_current_visual_context() -> dict:
    chat_history = st.session_state.get("chat_history", []) or []
    last_reply = ""

    try:
        for item in reversed(chat_history):
            if isinstance(item, tuple) and len(item) >= 2:
                role, content = item[0], item[1]
                if str(role).lower() == "assistant" and str(content or "").strip():
                    last_reply = str(content).strip()
                    break
            elif isinstance(item, dict):
                role = item.get("role", "")
                content = item.get("content", "")
                if str(role).lower() == "assistant" and str(content or "").strip():
                    last_reply = str(content).strip()
                    break
    except Exception:
        last_reply = ""

    facts = cached_get_facts(_usuario_key_atual()) or {}

    local = (
        _get_nested_fact(facts, "cena.local", "")
        or _get_nested_fact(facts, "state.local", "")
        or ""
    )

    roupa_mary = (
        _get_nested_fact(facts, "state.roupa", "")
        or ""
    )

    acao = (
        _get_nested_fact(facts, "cena.acao", "")
        or _get_nested_fact(facts, "state.assunto", "")
        or ""
    )

    emocao = str(st.session_state.get("image_emocao") or "").strip()

    return {
        "last_reply": last_reply,
        "local": str(local or ""),
        "roupa_mary": str(roupa_mary or ""),
        "emocao": emocao,
        "acao": str(acao or ""),
        "enquadramento": "medium shot",
        "iluminacao": "cinematic warm lighting",
        "extra": "",
        "extra_negative": "",
    }


def _init_state() -> None:
    defaults = {
        "visual_scene_summary": "",
        "visual_prompt": "",
        "visual_negative_prompt": "",
        "visual_last_image_bytes": None,
        "visual_last_image_text": "",
        "visual_seed": "",
        "visual_reference_url": "",
        "visual_extra": "",
        "visual_extra_negative": "",
        "visual_emotion": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def main() -> None:
    _apply_dark_ui()

    if not check_password():
        st.stop()

    _init_state()

    st.title("🎬 Mary Imagens")
    st.caption(f"Usuário: {_uid()} • Timeline: {_timeline()} • Key: {_usuario_key_atual()}")

    facts_now = cached_get_facts(_usuario_key_atual()) or {}

    with st.expander("📄 Contexto atual da cena", expanded=False):
        st.json(
            {
                "local": _get_nested_fact(facts_now, "cena.local", "") or _get_nested_fact(facts_now, "state.local", ""),
                "roupa": _get_nested_fact(facts_now, "state.roupa", ""),
                "acao": _get_nested_fact(facts_now, "cena.acao", "") or _get_nested_fact(facts_now, "state.assunto", ""),
                "timeline": _timeline(),
            }
        )

    c1, c2 = st.columns(2)

    with c1:
        if st.button("🛠️ Montar prompt automático", use_container_width=True):
            try:
                ctx = _get_current_visual_context()
                ctx["emocao"] = str(st.session_state.get("visual_emotion") or "").strip()
                ctx["extra"] = str(st.session_state.get("visual_extra") or "").strip()
                ctx["extra_negative"] = str(st.session_state.get("visual_extra_negative") or "").strip()

                built = build_prompt_from_scene_context(ctx)
                st.session_state["visual_scene_summary"] = built["scene_summary"]
                st.session_state["visual_prompt"] = built["prompt"]
                st.session_state["visual_negative_prompt"] = built["negative_prompt"]
                st.success("Prompt visual montado.")
                st.rerun()
            except Exception as e:
                st.error(f"Falha ao montar prompt: {type(e).__name__}: {e}")

    with c2:
        if st.button("🖼️ Gerar imagem", use_container_width=True):
            prompt_final = str(st.session_state.get("visual_prompt") or "").strip()
            negative_final = str(st.session_state.get("visual_negative_prompt") or "").strip()
            ref_url = str(st.session_state.get("visual_reference_url") or "").strip()
            seed_raw = str(st.session_state.get("visual_seed") or "").strip()

            seed = None
            if seed_raw:
                try:
                    seed = int(seed_raw)
                except Exception:
                    st.error("Seed inválida. Use apenas número inteiro.")
                    st.stop()

            if not prompt_final:
                st.error("Monte ou preencha o prompt antes de gerar.")
            else:
                with st.spinner("Gerando imagem..."):
                    try:
                        result = generate_image(
                            prompt=prompt_final,
                            negative_prompt=negative_final,
                            aspect_ratio="3:4",
                            image_size="1K",
                            seed=seed,
                            reference_images=[ref_url] if ref_url else None,
                        )

                        first = result["images"][0]
                        
                        image_url = ""
                        if isinstance(first, dict):
                            image_url_obj = first.get("image_url")
                            if isinstance(image_url_obj, dict):
                                image_url = str(image_url_obj.get("url") or "").strip()
                            elif isinstance(image_url_obj, str):
                                image_url = image_url_obj.strip()
                        
                        if not image_url:
                            raise RuntimeError(f"Campo image_url.url ausente no retorno: {first}")
                        
                        img_bytes = image_data_url_to_bytes(image_url)
                        st.session_state["visual_last_image_bytes"] = img_bytes
                        st.session_state["visual_last_image_text"] = result.get("text", "")
                        st.success("Imagem gerada com sucesso.")
                    except Exception as e:
                        st.error(f"Falha ao gerar imagem: {type(e).__name__}: {e}")

    st.markdown("**Emoção / clima da cena**")
    st.text_input(
        "emoção",
        key="visual_emotion",
        placeholder="Ex.: provocante, tensa, íntima, silenciosa",
        label_visibility="collapsed",
    )

    st.markdown("**Detalhes extras**")
    st.text_area(
        "detalhes_extras",
        key="visual_extra",
        height=80,
        placeholder="Ex.: luz lateral quente, bancada de mármore, vapor suave, olhar por cima do ombro",
        label_visibility="collapsed",
    )

    st.markdown("**Detalhes a evitar**")
    st.text_area(
        "detalhes_negativos_extras",
        key="visual_extra_negative",
        height=70,
        placeholder="Ex.: sem sorriso, sem fundo poluído, sem objetos extras",
        label_visibility="collapsed",
    )

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**Seed (opcional)**")
        st.text_input(
            "seed",
            key="visual_seed",
            placeholder="Ex.: 123456",
            label_visibility="collapsed",
        )

    with col_b:
        st.markdown("**URL de referência (opcional)**")
        st.text_input(
            "referencia",
            key="visual_reference_url",
            placeholder="https://...",
            label_visibility="collapsed",
        )

    st.markdown("**Resumo visual da cena**")
    novo_summary = st.text_area(
        "scene_summary",
        value=st.session_state.get("visual_scene_summary", ""),
        height=100,
        label_visibility="collapsed",
    )
    st.session_state["visual_scene_summary"] = novo_summary

    st.markdown("**Prompt visual atual**")
    novo_prompt = st.text_area(
        "visual_prompt",
        value=st.session_state.get("visual_prompt", ""),
        height=260,
        label_visibility="collapsed",
    )
    st.session_state["visual_prompt"] = novo_prompt

    st.markdown("**Prompt negativo**")
    novo_neg = st.text_area(
        "visual_negative_prompt",
        value=st.session_state.get("visual_negative_prompt", ""),
        height=100,
        label_visibility="collapsed",
    )
    st.session_state["visual_negative_prompt"] = novo_neg

    if st.session_state.get("visual_last_image_bytes"):
        st.image(
            st.session_state["visual_last_image_bytes"],
            caption="Imagem gerada",
            use_container_width=True,
        )

    texto_modelo = str(st.session_state.get("visual_last_image_text") or "").strip()
    if texto_modelo:
        st.caption(texto_modelo)


if __name__ == "__main__":
    main()
else:
    main()
