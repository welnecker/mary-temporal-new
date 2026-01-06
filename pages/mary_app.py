from __future__ import annotations

# ==========================================================
# IMPORTAÇÕES PADRÃƒO
# ==========================================================
tempo de importação
importar re
rastreamento de importação
import importlib
importação inspecionar
from typing import Any
importar streamlit como st

# ==========================================================
# ðŸ”¥ HARD RESET NO BOOT (ANTI-VAZAMENTO ENTRE TIMELINES)
# ==========================================================
def _hard_reset_on_boot_if_needed() -> None:
    """
    Streamlit reidrata session_state ao reabrir o aplicativo.
    Se a timeline mudou desde o último boot, limpamos TUDO
    antes de qualquer renderização.
    """
    current_tl = str(st.session_state.get("mary_timeline") or "cumplice").strip()
    last_tl = st.session_state.get("mary_last_boot_timeline")

    se last_tl != current_tl:
        para k em list(st.session_state.keys()):
            se não isinstance(k, str):
                continuar

            se k.startswith("_mary_service::"):
                st.session_state.pop(k, None)
                continuar

            se k.startswith(("facts::", "history::", "mem::", "longmem::")):
                st.session_state.pop(k, None)
                continuar

            se k.startswith(("intro_ctx_injected::", "intro_injected::")):
                st.session_state.pop(k, None)

        # âœ… evita ficar travado ao reabrir
        st.session_state.pop("mary_timeline_locked", None)
        st.session_state["mary_last_boot_timeline"] = current_tl


# âš ï¸ EXECUTA IMEDIATAMENTE NO BOOT
_hard_reset_on_boot_if_needed()

# ==========================================================
# IMPORTAÇÕES DO PROJETO (SEMPRE DEPOIS DO FUTURO)
# ==========================================================
from core.repositories import (
    lista_memórias,
    excluir_última_memória,
    excluir_todas_as_memórias,
    obter_documentos_de_histórico,
    obter_documentos_históricos_múltiplos,
    obter_fatos,
    definir_fato,
    append_memory, # âœ… necessário para o botão "virgem"
    excluir_fato,
    excluir_última_interação,
    excluir_histórico_do_usuário,
    # âœ… MEMÓRIA LONGA (busca de texto no MongoDB)
    adicionar_memória_longa,
    lista_memória_longa,
    pesquisar_texto_de_memória_longa,
    garantir_índices_de_memória_longa,
    excluir_última_memória_longa,
    excluir_toda_a_memória_longa,
)

import characters.mary.persona as mary_persona
from characters.mary.service import MaryService
import core.repositories as crep
import core.service_router as service_router
from core.database import db_status, ping_db, get_backend


# ==========================================================
# CONFIG
# ==========================================================
st.set_page_config(
    título_da_página="Roleplay",
    page_icon="ðŸ' ðŸ' ",
    layout="centralizado",
)

SENHA_CORRETA = "311071"
LIMITE_VISUAL_PADRÃO = 80

DEFAULT_MODEL = "tngtech/deepseek-r1t2-chimera:free"
FALLBACK_MODEL = "deepseek/deepseek-chat-v3-0324"


# ==========================================================
# UI / CSS (Base44-like + dark + chat_input)
# ==========================================================
def _apply_dark_ui() -> None:
    st.markdown(
        """
        <style>
        html, body, #root, .stApp { background: #0b0b0b !important; }
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stMainBlockContainer"] { background: #0b0b0b !important; }

        rodapé { visibilidade: oculta !importante; altura: 0 !importante; }

        /* espaço no fim para não esconder mensagens atrás do input fixo */
        .block-container {
            largura máxima: 980px !importante;
            padding-top: 1rem !important;
            padding-bottom: 9rem !important;
        }

        /* Cabeçalho do cartão */
        .rp-card {
            fundo: rgba(18,18,18,0.92);
            borda: 1px sólida rgba(255,255,255,0.10);
            raio da borda: 16px;
            preenchimento: 16px;
            margem: 0 0 12px 0;
            box-shadow: 0 12px 28px rgba(0,0,0,0.55);
            filtro de fundo: desfoque(6px);
        }
        .rp-title { tamanho da fonte: 22px; peso da fonte: 800; margem: 0; cor: #fff; }
        .rp-sub { tamanho da fonte: 13px; margem superior: 6px; cor: rgba(255,255,255,0.65); }

        /* Balões de bate-papo */
        div[data-testid="stChatMessage"] > div{
            fundo: rgba(15,15,15,0.92) !importante;
            borda: 1px sólida rgba(255,255,255,0.08) !importante;
            border-radius: 16px !important;
            preenchimento: 14px 14px 10px 14px !importante;
            box-shadow: 0 10px 26px rgba(0,0,0,0.55) !important;
        }
        div[data-testid="stChatMessage"][aria-label="user"] > div{
            fundo: rgba(24,24,24,0.95) !importante;
            borda: 1px sólida rgba(255,255,255,0.12) !importante;
        }
        div[data-testid="stChatMessage"]p{
            margem: 0 0 0,95rem 0 !importante;
            altura da linha: 1,55 !importante;
            tamanho da fonte: 1,02rem !importante;
            cor: #f2f2f2 !importante;
        }

        /* ENTRADA FIXO */
        .stChatInput, div[data-testid="stChatInput"] {
            posição: fixa !importante;
            esquerda: 0 !importante;
            direita: 0 !importante;
            parte inferior: 0 !importante;
            z-index: 9999 !importante;
            fundo: rgba(11,11,11,0.88) !importante;
            backdrop-filter: blur(10px) !important;
            borda superior: 1px sólida rgba(255,255,255,0.10) !importante;
            preenchimento: 10px 0 !importante;
        }

        .stChatInput > div, div[data-testid="stChatInput"] > div {
            largura máxima: 980px !importante;
            margem: 0 auto !importante;
            preenchimento: 0 1rem !importante;
        }

        .stChatInput textarea, div[data-testid="stChatInput"] textarea {
            altura mínima: 96px !importante;
            altura máxima: 240px !importante;
            border-radius: 14px !important;
            fundo: #101010 !importante;
            cor: #f2f2f2 !importante;
            borda: 1px sólida rgba(255,255,255,0.14) !importante;
        }
        </style>
        "",
        unsafe_allow_html=True,
    )


def _format_paragraphs(text: str) -> str:
    t = (texto ou "").strip()
    se não t:
        retornar t
    se "\n\n" em t:
        retornar t

    se "\n" em t e t.count("\n") >= 2:
        t2 = re.sub(r"\n{2,}", "\n\n", t)
        se "\n\n" em t2:
            retornar t2
        t = t2.replace("\n", " ")

    frases = re.split(r"(?<=[.!?â€¦])\s+", t)
    frases = [s.strip() para s em frases se s.strip()]
    se len(sentences) <= 3:
        retornar t

    pedaços = []
    i = 0
    enquanto i < len(sentenças):
        tamanho = 2 se (i % 6) != 4 senão 3
        chunk = " ".join(sentences[i : i + size]).strip()
        se bloco:
            chunks.append(chunk)
        i += tamanho

    retornar "\n\n".join(chunks)


# ==========================================================
# SENHA
# ==========================================================
def verificar_senha() -> bool:
    se "senha_ok" não estiver em st.session_state:
        st.session_state["senha_ok"] = Falso
    se st.session_state["senha_ok"]:
        retornar Verdadeiro

    _apply_dark_ui()
    st.title("ðŸ” Acesso Restrito")
    com st.form("form_senha", clear_on_submit=False):
        senha = st.text_input("Digite a senha de acesso:", type="password")
        ok = st.form_submit_button("Entrar")

    Se estiver tudo bem:
        se senha == SENHA_CORRETA:
            st.session_state["senha_ok"] = True
            st.success("Acesso liberado!")
            st.rerun()
        outro:
            st.error("Senha incorreta. Tente novamente.")
    retornar Falso


se não check_password():
    st.stop()


# ==========================================================
# KEYS (não depende do serviço)
# ==========================================================
def _uid() -> str:
    uid = (st.session_state.get("user_id") or "anon").strip() or "anon"
    retornar uid


def _timeline() -> str:
    retornar str(st.session_state.get("mary_timeline") ou "cumplice").strip() ou "cumplice"


def _usuario_key_atual() -> str:
    retornar f"{_uid()}::mary::{_timeline()}"


def _usuario_key_for_timeline(timeline: str) -> str:
    tl = str(timeline or "cumplice").strip() or "cumplice"
    retornar f"{_uid()}::mary::{tl}"


def _shared_key_atual() -> str:
    retornar f"{_uid()}::mary::shared"


def _keys_para_mary() -> list[str]:
    # âœ… SEMPRE somente a timeline ativa
    retornar [_usuario_key_atual()]


# ==========================================================
# âœ… AJUDANTES DO BOTÃO CANON (Virgem -> Consumado)
# ==========================================================
def _today_iso() -> str:
    retornar time.strftime("%Y-%m-%d", time.localtime())


def _set_virginity_canon(*, usuario_key: str, shared_key: str, timeline: str, user_id: str) -> None:
    """
    Marca no CANON que Mary NÃƒO Ã© mais virgem (consumado).
    - Grava na memória permanente compartilhada como kind='canon' (fonte de verdade).
    - Atualiza rel.state::<timeline> nos fatos (camada derivada, para consistência imediata).
    """
    data_iso = _today_iso()

    texto_canônico = (
        f"MEMÓRIA CANÔNICA: Mary e {user_id} consumiram a relação. "
        f"Mary NÃƒO Ã© mais virgem. (vÃ¡lido para o universo compartilhado)\n"
        f"Dados: {date_iso}\n"
        f"Timeline ativa no momento do registro: {timeline}"
    )

    meta = {
        "tipo": "cânone",
        "title": "Virgindade — consumado",
        "chave": "virgindade",
        "valor": "nao_virgem",
        "data": data_iso,
        "origem": "ui_button",
        "timeline_at_save": linha do tempo,
        "user_id": user_id,
    }

    # 1) CANON (compartilhado)
    append_memory(shared_key, canon_text, meta=meta)

    # 2) FATOS (estado_de_relacionamento) — derivado
    fatos = obter_fatos(chave_do_usuário) ou {}
    rel_key = f"rel.state::{timeline}"
    rel = facts.get(rel_key) if isinstance(facts.get(rel_key), dict) else {}

    se não isinstance(rel, dict):
        rel = {}

    rel["consumado"] = Verdadeiro
    rel["virgindade"] = "nao_virgem"
    rel.setdefault("allows_penetration", True)

    set_fact(usuario_key, rel_key, rel, {"fonte": "ui_button_canon"})
    set_fact(usuario_key, "mary.virginity", "nao_virgem", {"fonte": "ui_button_canon"})


# ==========================================================
# AJUDANTES
# ==========================================================
def _service_key_for_userkey(userkey: str) -> str:
    retornar f"_mary_service::{userkey}"


def _instantiate_mary_service(*, userkey: str, timeline: str) -> MaryService:
    """
    Cria MaryService de forma compatível com diferentes assinaturas.
    - Se MaryService aceitar (usuario_key, timeline), use.
    - Se aceitar sÃ³ (usuario_key) ou sÃ³ (timeline), use o que existir.
    - Caso não aceite nada, instância vazia.
    """
    tentar:
        sig = inspect.signature(MaryService.__init__)
        params = set(sig.parameters.keys()) # inclui "self"
    exceto Exceção:
        parâmetros = conjunto()

    kwargs: dict[str, Any] = {}
    se "usuario_key" em params:
        kwargs["usuario_key"] = chave do usuário
    se "user_key" estiver em params:
        kwargs["user_key"] = userkey
    se "timeline" estiver em params:
        kwargs["timeline"] = linha do tempo

    tentar:
        retornar MaryService(**kwargs) se kwargs senão MaryService()
    exceto TypeError:
        tentar:
            retornar MaryService()
        exceto Exceção:
            tentar:
                retornar MaryService(userkey) # tipo: ignorar
            exceto Exceção:
                retornar MaryService() # tipo: ignorar


def _get_service() -> MaryService:
    """
    âœ… FIX DO VAZAMENTO:
    Serviço é isolado por usuario_key (que inclui cronograma).
    Linha do tempo Trocar => outro serviço.
    """
    Reino Unido = _usuario_key_atual()
    tl = _timeline()

    sk = _service_key_for_userkey(uk)
    svc = st.session_state.get(sk)

    Se svc for None:
        svc = _instantiate_mary_service(userkey=uk, timeline=tl)
        st.session_state[sk] = svc

    retornar svc


def _kill_all_mary_services() -> None:
    para k em list(st.session_state.keys()):
        se isinstance(k, str) e k.startswith("_mary_service::"):
            st.session_state.pop(k, None)


def _invalidate_backend_cache() -> None:
    st.session_state["backend_hist_cache"] = None
    st.session_state["backend_hist_cache_ts"] = 0.0
    st.session_state["backend_hist_cache_key"] = ""

    # âœ… também derrubaram cache de memórias do serviço
    sk = _shared_key_atual()
    prefix_mem = f"mem::{sk}::"
    para k em list(st.session_state.keys()):
        se isinstance(k, str) e k.startswith(prefix_mem):
            st.session_state.pop(k, None)


def _choose_default_model(available: list[str]) -> str:
    se disponível e DEFAULT_MODEL estiver disponível:
        retornar DEFAULT_MODEL
    se disponível:
        não_grok = [m para m em disponível se "grok" não estiver em (m ou "").lower()]
        retorna non_grok[0] se non_grok senão available[0]
    retornar FALLBACK_MODEL


def _garantir_estado_inicial() -> Nenhum:
    # timeline precisa existir ANTES de qualquer chave
    se "mary_timeline" não estiver em st.session_state:
        st.session_state["mary_timeline"] = "cumplice"
    se "mary_timeline_locked" não estiver em st.session_state:
        st.session_state["mary_timeline_locked"] = False

    se "user_id" não estiver em st.session_state ou não estiver em st.session_state["user_id"]:
        st.session_state["user_id"] = "Janio Donisete"

    se "chat_history" não estiver em st.session_state:
        st.session_state["chat_history"] = []

    se "backend_hist_cache_key" não estiver em st.session_state:
        st.session_state["backend_hist_cache_key"] = ""

    # Depuração de relacionamento
    se "mary_debug_rel_panel" não estiver em st.session_state:
        st.session_state["mary_debug_rel_panel"] = False
    se "mary_rel_meta_last" não estiver em st.session_state:
        st.session_state["mary_rel_meta_last"] = None

    # modelo disponíveis
    tentar:
        modelos = service_router.list_models() ou []
    exceto Exceção:
        modelos = []

    se "model" não estiver em st.session_state ou não estiver em st.session_state["model"]:
        st.session_state["model"] = _choose_default_model(modelos)
    outro:
        Se modelos e st.session_state["model"] não estiverem em modelos:
            st.session_state["model"] = _choose_default_model(modelos)

    # NSFW padrão por linha do tempo
    se "mary_nsfw_on" não estiver em st.session_state:
        st.session_state["mary_nsfw_on"] = (_timeline() != "universitaria")

    # para detectar mudanças e persistir sem loop
    se "mary_nsfw_last_saved" não estiver em st.session_state:
        st.session_state["mary_nsfw_last_saved"] = None

    se "mary_intro_done" não estiver em st.session_state:
        st.session_state["mary_intro_done"] = False
    se "visual_limit" não estiver em st.session_state:
        st.session_state["visual_limit"] = DEFAULT_VISUAL_LIMIT
    se "backend_hist_cache" não estiver em st.session_state:
        st.session_state["backend_hist_cache"] = None
    se "backend_hist_cache_ts" não estiver em st.session_state:
        st.session_state["backend_hist_cache_ts"] = 0.0

    # debounce
    se "last_submit_ts" não estiver em st.session_state:
        st.session_state["last_submit_ts"] = 0.0
    se "last_submit_text" não estiver em st.session_state:
        st.session_state["last_submit_text"] = ""

    # vista de memórias
    se "__mem_list" não estiver em st.session_state:
        st.session_state["__mem_list"] = None


def _clear_service_caches_for_keys(keys: list[str]) -> None:
    # âœ… remover fatos + TODOS histórico::<chave>::<limite> + mem::<chave>::<limite>
    para k em chaves:
        # fatos
        fk = f"fatos::{k}"
        se fk estiver em st.session_state:
            del st.session_state[fk]

        # história
        prefix_hist = f"history::{k}::"
        para sk em list(st.session_state.keys()):
            se isinstance(sk, str) e sk.startswith(prefix_hist):
                st.session_state.pop(sk, None)

        # âœ… cache de memória
        prefix_mem = f"mem::{k}::"
        para sk em list(st.session_state.keys()):
            se isinstance(sk, str) e sk.startswith(prefix_mem):
                st.session_state.pop(sk, None)


def _reset_intro_flags_for_keys(keys: list[str]) -> None:
    para k em chaves:
        st.session_state.pop(f"intro_ctx_injected::{k}", None)
        st.session_state.pop(f"intro_injected::{k}", None)


def _clear_mary_caches_all_related(*, also_clear_other_timeline: bool = True) -> None:
    """
    Limpa caches do usuario_key atual e do shared_key.
    Para evitar o “vazamento visual” na troca de timeline, também limpe a OUTRA timeline.
    """
    Reino Unido = _usuario_key_atual()
    sk = _shared_key_atual()

    chaves = [uk, sk]

    se também_limpar_outra_linha_do_tempo:
        other = "universitaria" if _timeline() == "cumplice" else "cumplice"
        keys.append(_usuario_key_for_timeline(other))

    _limpar_caches_de_serviço_para_chaves(chaves)
    _reset_intro_flags_for_keys(keys)


def _persist_nsfw_for_current_timeline_if_needed_inline() -> None:
    """
    Persistência NSFW INLINE (não depende de helper fora do callback).
    Evita NameError em callback antigo preso na sessão.
    """
    Reino Unido = _usuario_key_atual()
    atual = bool(st.session_state.get("mary_nsfw_on", False))
    último = st.session_state.get("mary_nsfw_last_saved", None)

    se last for None ou bool(last) != current:
        tentar:
            set_fact(uk, "mary.nsfw", current, {"fonte": "ui_toggle"})
        exceto Exceção:
            passar
        st.session_state["mary_nsfw_last_saved"] = atual
        _limpar_caches_de_serviço_para_chaves([uk])


def _sort_backend_docs(docs: list[dict]) -> list[dict]:
    """
    âœ… Corrige â€œnÃ£o retorna na posiÃ§Ã£o corretaâ€ .
    Ordene pelo melhor timestamp disponível, mantendo a estabilidade.
    """
    se não houver documentos:
        devolver documentos

    def _ts(d: dict) -> float:
        para k em ("ts", "timestamp", "created_ts", "created_at", "time", "date"):
            v = d.get(k)
            se v for None:
                continuar
            se isinstance(v, (int, float)):
                retornar float(v)
            se isinstance(v, str):
                tentar:
                    vv = v.replace("T", " ").replace("Z", "").strip()
                    se vv.édigito():
                        retornar float(vv)
                exceto Exceção:
                    passar
        retornar 0.0

    indexado = lista(enumerar(docs))
    indexado.sort(chave=lambda it: (_ts(it[1]), it[0]))
    retornar [d para _, d em indexado]


def _carregar_chat_visual_do_backend(force: bool = False) -> list[tuple[str, str]]:
    agora = tempo.tempo()
    chaves = _chaves_para_maria()
    cache_key = "|".join(keys)

    se não for forçado:
        cached = st.session_state.get("backend_hist_cache")
        ts = float(st.session_state.get("backend_hist_cache_ts", 0.0))
        ck = str(st.session_state.get("backend_hist_cache_key", ""))
        se cached não for None e (agora - ts) < 2.0 e ck == cache_key:
            retornar em cache

    tentar:
        docs = get_history_docs_multi(keys, limit=800) or []
        docs = _sort_backend_docs(docs)
    exceto Exception como e:
        st.session_state["last_model_error"] = f"Falha ao carregar o histórico de inicialização: {type(e).__name__}: {e}"
        st.error("ðŸ'¥ Falha ao carregar histórico do backend.")
        st.write("Chaves consultadas:", chaves)
        st.code(traceback.format_exc())
        st.stop()

    hist: lista[tupla[str, str]] = []
    para d em docs:
        u = (d.get("mensagem_usuario") ou "").strip()
        a = (d.get("resposta_mary") ou "").strip()
        se você:
            hist.append(("user", u))
        se a:
            hist.append(("assistente", a))

    st.session_state["backend_hist_cache"] = hist
    st.session_state["backend_hist_cache_ts"] = agora
    st.session_state["backend_hist_cache_key"] = cache_key
    retornar histórico


def _apagar_hist_bd_novo_e_legado() -> int:
    chaves = _chaves_para_maria()
    total = 0
    para k em chaves:
        tentar:
            total += int(excluir_histórico_do_usuário(k) ou 0)
        exceto Exceção:
            passar
    retornar total


def _diagnostico_hist(keys: list[str]) -> dict:
    saída = {}
    para k em chaves:
        tentar:
            docs = get_history_docs(k, limit=5) ou []
            docs = _sort_backend_docs(docs)
            saída[k] = {
                "count_approx_5": len(docs),
                "first_user": (docs[0].get("mensagem_usuario") if docs else None),
                "first_mary": (docs[0].get("resposta_mary") if docs else None),
                "last_user": (docs[-1].get("mensagem_usuario") if docs else None),
                "last_mary": (docs[-1].get("resposta_mary") if docs else None),
            }
        exceto Exception como e:
            out[k] = {"error": f"{type(e).__name__}: {e}"}
    retornar para fora


def _apagar_eventos_mary_fact(usuario_key: str) -> int:
    tentar:
        fatos = obter_fatos(chave_do_usuário) ou {}
    exceto Exceção:
        fatos = {}

    chaves = [
        k
        para k em facts.keys()
        se isinstance(k, str) e (k.startswith("mary.evento.") ou k.startswith("mary.eventos."))
    ]
    removido = 0
    para k em chaves:
        tentar:
            if delete_fact(usuario_key, k):
                removido += 1
        exceto Exceção:
            passar
    retorno removido


def _delete_last_turn_active() -> bool:
    usuario_key = _usuario_key_atual()
    tentar:
        ok = bool(excluir_última_interação(chave_do_usuário))
    exceto Exceção:
        ok = Falso

    _invalidate_backend_cache()
    _limpar_caches_de_todos_os_relacionados_da_mary()
    retornar ok


def _reset_chapter_current_timeline() -> int:
    """
    Reset de capítulo: apaga o histórico da timeline atual,
    mantém memórias permanentes (compartilhadas).
    """
    Reino Unido = _usuario_key_atual()
    n = 0
    tentar:
        n = int(excluir_histórico_do_usuário(reino Unido) ou 0)
    exceto Exceção:
        passar

    st.session_state["chat_history"] = []
    st.session_state["mary_intro_done"] = False
    _invalidate_backend_cache()
    _limpar_caches_de_todos_os_relacionados_da_mary()
    st.session_state["mary_timeline_locked"] = False
    retornar n


def _unlock_timeline_and_reset_chapter() -> None:
    """Destrava a linha do tempo e reinicia o capítulo atual (mantém memórias compartilhadas/canon)."""
    _reset_chapter_current_timeline()
    # extra segurança: matar serviços e caches
    _matar_todos_os_serviços_da_Maria()
    _invalidate_backend_cache()
    _limpar_caches_de_todos_os_relacionados_da_mary()


def _on_timeline_change() -> None:
    """
    âœ… Anti-vazamento + anti-NameError:
    - Limpa caches faz backend + serviço + visual.
    - Persiste NSFW inline (sem depender de helper externo no callback).
    - MATA serviços isolados por usuario_key (para garantir troca limpa).
    """

    personas = {
        "Maria – Esposa Cúmplice": "cumplice",
        "Mary – Universitária (linha alternativa)": "universitaria",
    }

    old_tl = str(st.session_state.get("mary_timeline") or "cumplice").strip() or "cumplice"
    novo_tl = personas.get(st.session_state.get("persona_label") or "", "cumplice")

    # troca linha do tempo
    st.session_state["mary_timeline"] = new_tl

    # padrão NSFW por linha do tempo
    st.session_state["mary_nsfw_on"] = (new_tl != "universitaria")

    # âœ… Persistência NSFW (inline)
    _persist_nsfw_for_current_timeline_if_needed_inline()

    # limpa visual + caches (inclui timeline antiga para matar vazamento)
    st.session_state["chat_history"] = []
    st.session_state["mary_intro_done"] = False
    _invalidate_backend_cache()
    _clear_mary_caches_all_related(also_clear_other_timeline=True)
    _limpar_caches_de_serviços_para_chaves([_chave_do_usuário_para_linha_do_tempo(old_tl), _chave_do_usuário_para_linha_do_tempo(new_tl)])

    # ðŸ”¥ ponto crítico: matar instâncias de serviço para não reaproveitar estado
    _matar_todos_os_serviços_da_Maria()


def _get_intro_persona_text(timeline: str) -> str:
    """
    Busca a primeira mensagem ‘assistente’ da persona para a timeline.
    Retorna fallback se não achar.
    """
    tentar:
        _, boot = mary_persona.get_persona(timeline)
    exceto Exceção:
        inicialização = Nenhum

    introdução = ""
    se isinstance(boot, list):
        para m em boot:
            se não isinstance(m, dict):
                continuar
            se m.get("role") != "assistant":
                continuar
            if str(m.get("timeline") or "").strip() != str(timeline or "").strip():
                continuar
            c = (m.get("content") ou "").strip()
            se c:
                introdução = c
                quebrar

    se não for introdução:
        intro = "Eu já estava ali quando você chegou. Eu te vejo e espero sua atitude."

    retornar intro.strip()


def _inject_intro_visual_if_needed() -> None:
    """
    Injetar uma introdução visual somente se backend não tem histórico
    e chat_history está vazio.
    """
    se st.session_state.get("mary_intro_done", False):
        retornar

    se st.session_state.get("chat_history"):
        st.session_state["mary_intro_done"] = True
        retornar

    backend_hist = _carregar_chat_visual_do_backend(force=False)
    se backend_hist:
        st.session_state["chat_history"] = backend_hist
        st.session_state["mary_intro_done"] = True
        retornar

    tl = _timeline()
    intro = _get_intro_persona_text(tl)

    st.session_state["chat_history"] = [("assistant", intro)]
    st.session_state["mary_intro_done"] = True


def _boot_visual_if_empty() -> None:
    se st.session_state.get("chat_history"):
        st.session_state["mary_intro_done"] = True
        retornar

    backend_hist = _carregar_chat_visual_do_backend(force=False)
    se backend_hist:
        st.session_state["chat_history"] = backend_hist
        st.session_state["mary_intro_done"] = True
        retornar

    st.session_state["chat_history"] = []
    st.session_state["mary_intro_done"] = False
    _inject_intro_visual_if_needed()


def _auto_unlock_if_sem_interacao() -> None:
    """
    âœ… Resolva o seu caso: menu já abre travado na 'cumplice'.
    Se NÃƒO hÃ¡ nenhuma mensagem do usuÃ¡rio (nem no visual, nem no backend),
    destrava automaticamente para permitir escolher 'universitaria'.
    """
    se não st.session_state.get("mary_timeline_locked", False):
        retornar

    # se já teve usuário no visual, mantém travado
    hist = st.session_state.get("chat_history") ou []
    se algum(r == "usuário" para r, _ em hist):
        retornar

    # se existe usuário no backend, mantém travado
    tentar:
        docs = get_history_docs(_usuario_key_atual(), limit=3) or []
    exceto Exceção:
        docs = []

    para d em docs:
        se (d.get("mensagem_usuario") ou "").strip():
            retornar

    st.session_state["mary_timeline_locked"] = False


# ==========================================================
# Aplicativo
# ==========================================================
def main() -> None:
    _apply_dark_ui()
    _garantir_estado_inicial()
    _auto_unlock_if_sem_interacao()

    st.caption("ðŸ§© mary_app.py v3.13 (serviço isolado por timeline + anti-vazamento hard + botão CANON virgem)")
    backend, detalhe = db_status()
    st.caption(f"ðŸ—„ï¸ Backend atual: **{backend}** ({detail})")

    # ==========================================================
    # ðŸ—„ï¸ DEBUG — BANCO DE DADOS (db_status + ping_db)
    # ==========================================================
    com st.expander("ðŸ—„ï¸ Banco de Dados â— Debug (db_status + ping_db)", expanded=False):
        b_kind, b_detail = db_status()
        st.write("**db_status():**")
        st.code(f"{b_kind} â— {b_detail}")

        colA, colB, colC = st.columns([1, 1, 1])
        com colA:
            executar_ping = st.button("ðŸ”Ž Rodar ping_db()", key="btn_run_ping_db")
        com colB:
            auto_ping = st.checkbox("Ping automático (a cada nova execução)", value=False, key="chk_auto_ping_db")
        com colC:
            show_env = st.checkbox("Mostrar config (mascarada)", value=False, key="chk_show_db_env")

        se run_ping ou auto_ping:
            backend, ok, info = ping_db()
            st.write("**ping_db():**")
            Se estiver tudo bem:
                st.success(f"{backend} âœ… {info}")
            outro:
                st.error(f"{backend} â Œ {info}")

        se show_env:
            tentar:
                from core.config import settings as _settings # type: ignore

                uri = ""
                tentar:
                    uri = str(_settings.mongo_uri() ou "")
                exceto Exceção:
                    uri = ""

                def _mask_uri(u: str) -> str:
                    u = u.strip()
                    se não você:
                        retornar ""
                    u = re.sub(r"//([^:/@]+):([^@]+)@", r"//***:***@", u)
                    se "?" em u:
                        base, _q = u.split("?", 1)
                        retornar base + "?"â€·..."
                    retornar u

                dbname = (getattr(_settings, "MONGO_DB", "") ou "").strip() ou getattr(_settings, "APP_NAME", "app")
                st.write("**Configuração:**")
                st.json(
                    {
                        "DB_BACKEND (configurações/ambiente)": (getattr(_settings, "DB_BACKEND", "") ou ""),
                        "get_backend() (runtime)": get_backend(),
                        "mongo_uri() (mascarada)": _mask_uri(uri),
                        "MONGO_DB ou APP_NAME": nome_do_banco_de_dados,
                    }
                )
            exceto Exception como e:
                st.warning(f"Não consegui ler configurações para debug: {type(e).__name__}: {e}")

    # ===== Cabeçalho =====
    st.markdown(
        f"""
        <div class="rp-card">
          <div class="rp-title">Mary ðŸ' ðŸ' </div>
          <div class="rp-sub">
            Linha do tempo: <b>{_timeline()_fulb> •
            Modelo: <b>{st.session_state.get('model','')}</b>
          </div>
        </div>
        "",
        unsafe_allow_html=True,
    )

    personas = {
        "Maria – Esposa Cúmplice": "cumplice",
        "Mary – Universitária (linha alternativa)": "universitaria",
    }

    rótulo_atual = próximo(
        (k para k, v em personas.items() se v == _timeline()),
        "Maria – Esposa Cúmplice",
    )

    st.selectbox(
        "ðŸŽ Linha temporal da Maria",
        lista(personas.keys()),
        índice=lista(personas.keys()).index(rótulo_atual),
        desativado=Falso,
        chave="rótulo_da_persona",
        on_change=_on_timeline_change,
    )

    se st.session_state["mary_timeline_locked"]:
        st.caption("ðŸ”' Persona travada após a 1ª mensagem do usuário.")
        st.caption("ðŸ'‰ Se travou sem você ter falado nada, use: Sidebar → 'Destravar timeline'.")

    chaves = _chaves_para_maria()

    # ==========================================================
    # âœ… RELAÇÃO DE DEPURAÇÃO DO PAINEL (ÁREA PRINCIPAL) — SOMENTE LEITURA
    # ==========================================================
    with st.expander("ðŸ§ Mecanismo de Relacionamento — Painel de diagnóstico (turno a turn)", expandido=False):
        col1, col2 = st.columns([1, 1])

        com col1:
            habilitado = bool(st.session_state.get("mary_debug_rel_panel", False))
            st.caption(
                "Ative em **Sidebar → Debug → Mostrar painel Relationship** â€¢ "
                f"Status: **{'LIGADO' se ativado, caso contrário, 'DESLIGADO'}**"
            )
            st.caption("Fonte: st.session_state['mary_rel_meta_last'] (gravado pelo service.py após cada resposta).")

        com col2:
            if st.button("Limpar diagnóstico (só visual)", key="btn_clear_rel_diag_main"):
                st.session_state["mary_rel_meta_last"] = None
                st.success("Diagnóstico limpo.")

        último = st.session_state.get("mary_rel_meta_last")

        se não estiver ativado:
            st.info("Painel desativado. Ativo na barra lateral para ver o diagnóstico a cada turno.")
        outro:
            se não for o último:
                st.warning("Ainda não há diagnóstico. Envie uma mensagem e depois volte aqui.")
            outro:
                cA, cB, cC, cD = st.columns(4)
                com cA:
                    st.metric("Linha do tempo", str(last.get("linha do tempo") ou "--"))
                com cB:
                    st.metric("Stage", str(last.get("stage") or "â--"))
                com cC:
                    st.metric("Curvas maduras", str(last.get("curvas_maduras") or 0))
                com cD:
                    hp = último.obter("hazard_p")
                    st.metric("Hazard P", f"{hp:.2f}" if isinstance(hp, (int, float)) else "â--"

                st.markdown("---")
                c1, c2, c3 = st.columns(3)
                com c1:
                    st.metric("Virgindade", str(last.get("virgindade") ou "—"))
                com c2:
                    st.metric("Consumado", "true" if last.get("consumado") else "false"
                com c3:
                    st.metric("Virgindade alterada", "true" if last.get("virginity_changed") else "false")

                motivo = (último.obter("motivo_da_virgindade") ou "").strip()
                se houver motivo:
                    st.caption("Motivo (motivo_da_virgindade):")
                    st.code(motivo)

                st.caption("Despejo bruto:")
                st.json(último)

    # ==========================================================
    # BACKEND RESET / DIAGNÓSTICO
    # ==========================================================
    with st.expander("ðŸ§¨ BACKEND — apagar histórico de verdade + diagnóstico", expandido=Falso):
        st.write("Chaves usadas:", keys)

        if st.button("ðŸ”Ž Diagnóstico agora", key="btn_diag_now"):
            st.json(_diagnostico_hist(keys))

        st.markdown("### Reset de capítulo / reset total")

        colX, colY = st.columns(2)
        com colX:
            if st.button("ðŸ§¼ Reset capÃtulo (apagar history da timeline ativa)", key="btn_reset_chapter"):
                n = _reset_chapter_current_timeline()
                st.success(f"âœ… Capítulo redefinido. Apaguei {n} registros de histórico da timeline ativa.")
                st.rerun()

        com colY:
            confirmar_total = st.checkbox(
                "Confirmar RESET TOTAL (histórico + eventos opcionais + memórias opcionais compartilhadas)",
                valor=Falso,
                chave="chk_confirm_total_reset",
            )
            delete_events = st.checkbox("Também apagar fatos mary.evento.*", value=False, key="chk_total_del_events")
            excluir_compartilhado = st.checkbox(
                "Também apagar TODAS memórias permanentes (shared)", value=False, key="chk_total_del_shared"
            )

            if st.button("ðŸ”¥ REDEFINIR TOTAL AGORA", type="primary", key="btn_total_reset_now"):
                se não confirmar_total:
                    st.error("Marque a confirmação do RESET TOTAL.")
                outro:
                    n_hist = _apagar_hist_bd_novo_e_legado()

                    n_evt = 0
                    se delete_events:
                        n_evt = _apagar_eventos_mary_fact(_usuario_key_atual())

                    n_mems = 0
                    se delete_shared:
                        tentar:
                            n_mems = int(delete_all_memories(_shared_key_atual()) or 0)
                        exceto Exceção:
                            n_mems = 0
                        st.session_state["__mem_list"] = []

                    st.session_state["chat_history"] = []
                    st.session_state["mary_intro_done"] = False
                    st.session_state["mary_timeline_locked"] = False
                    st.session_state["mary_rel_meta_last"] = None
                    _invalidate_backend_cache()
                    _limpar_caches_de_todos_os_relacionados_da_mary()
                    _matar_todos_os_serviços_da_Maria()

                    st.success(f"âœ… RESET TOTAL concluído. history={n_hist} | eventos={n_evt} | mems_shared={n_mems}")
                    st.rerun()

    # ==========================================================
    # BARRA LATERAL
    # ==========================================================
    com st.sidebar:
        st.header("Mary – Controles")

        st.text_input(
            "ðŸ'¤ Usuário",
            valor=st.session_state.get("user_id", "Janio Donisete"),
            desativado=Verdadeiro,
            chave="inp_user_disabled",
        )
        st.caption(f"Linha do tempo: {_timeline()}")
        st.caption(f"ðŸ”' usuario_key atual: {_usuario_key_atual()}")

        # âœ…botão para resolver travamento sem apagar BD
        se st.session_state.get("mary_timeline_locked", False):
            if st.button("ðŸ”“ Linha do tempo do Destravar (visual)", key="btn_unlock_timeline_visual"):
                st.session_state["mary_timeline_locked"] = False
                st.session_state["chat_history"] = []
                st.session_state["mary_intro_done"] = False
                _invalidate_backend_cache()
                _clear_mary_caches_all_related(also_clear_other_timeline=True)
                _matar_todos_os_serviços_da_Maria()
                st.rerun()

        tentar:
            todos_os_modelos = service_router.list_models() ou []
        exceto Exceção:
            todos_os_modelos = []

        se não todos os modelos:
            todos_os_modelos = [MODELO_DE_CONTRAÇÃO]

        se st.session_state.get("model") não estiver em all_models:
            st.session_state["model"] = _choose_default_model(all_models)

        atual = st.session_state.get("modelo")
        idx = all_models.index(current) se current estiver em all_models senão 0

        st.selectbox(
            "ðŸ§ Modelo",
            todos_os_modelos,
            índice=idx,
            chave="modelo",
        )

        st.markdown("---")
        # âœ… NSFW: persistir sem fatos quando muda (INLINE)
        nsfw_before = bool(st.session_state.get("mary_nsfw_on", False))
        st.checkbox("Modo adulto liberado (NSFW)", key="mary_nsfw_on")
        nsfw_after = bool(st.session_state.get("mary_nsfw_on", False))
        se nsfw_after != nsfw_before:
            _persist_nsfw_for_current_timeline_if_needed_inline()

        # ======================================================
        # âœ… BOTÃO "VIRGEM" (CANON) — gravar consumido
        # ======================================================
        st.markdown("---")
        st.subheader("ðŸ§¬ Canon — Estado Íntimo")

        uk_now = _usuario_key_atual()
        tl_now = _timeline()
        sk_now = _shared_key_atual()
        uid_now = str(st.session_state.get("user_id", "Janio Donisete"))

        tentar:
            fatos_agora = obter_fatos(reino_britânico_agora) ou {}
        exceto Exceção:
            fatos_agora = {}

        rel_now = (
            facts_now.get(f"rel.state::{tl_now}")
            se isinstance(facts_now.get(f"rel.state::{tl_now}"), dict)
            outro {}
        )
        is_consumado = bool(rel_now.get("consumado")) or (str(rel_now.get("virginidade") or "") == "nao_virgem")

        label_btn = "âœ… Virgem (marcar CONSUMADO)" if not is_consumado else "ðŸ”¥ Consumado (manter)"

        if st.button(label_btn, key="btn_canon_virginity_consumado"):
            tentar:
                se não for_consumido:
                    _set_virginity_canon(
                        usuario_key=uk_now,
                        shared_key=sk_now,
                        linha do tempo=tl_agora,
                        user_id=uid_now,
                    )

                st.session_state["chat_history"] = []
                st.session_state["mary_intro_done"] = False
                _invalidate_backend_cache()
                _clear_mary_caches_all_related(also_clear_other_timeline=True)
                _matar_todos_os_serviços_da_Maria()

                st.success("âœ… CANON atualizado: Mary NÃƒO Ã© mais virgem (consumado).")
                st.rerun()

            exceto Exception como e:
                st.error(f"Falha ao gravar CANON: {type(e).__name__}: {e}")

        st.caption("Obs.: Reset capítulo não apaga canon. Reset total com apagar memórias compartilhadas apaga.")

        st.markdown("---")
        st.subheader("ðŸ” Depuração")

        st.session_state["mary_debug_rel_panel"] = st.checkbox(
            "Mostrar painel Relacionamento",
            valor=bool(st.session_state.get("mary_debug_rel_panel", False)),
            chave="mary_debug_rel_panel__ui",
        )

        if st.button("Ver último diagnóstico (popup)", key="btn_show_rel_diag_popup"):
            último = st.session_state.get("mary_rel_meta_last")
            se for o último:
                st.json(último)
            outro:
                st.info("Ainda não existe mary_rel_meta_last.")

        st.markdown("---")
        st.subheader("Turnos")

        if st.button("Apagar último turno (backend)", key="btn_delete_last_turn"):
            ok = _excluir_último_turno_ativo()
            Se estiver tudo bem:
                st.session_state["chat_history"] = []
                st.session_state["mary_intro_done"] = False
                st.success("âœ…último turno desativado (timeline ativa).")
            outro:
                st.warning("Nada para apagar (backend não retornou sucesso).")
            st.rerun()

        st.markdown("---")
        st.subheader("Limpar tela")
        if st.button("Limpar tela (visual)", key="btn_clear_screen_visual"):
            st.session_state["chat_history"] = []
            st.rerun()

        st.markdown("---")
        st.subheader("ðŸŽ Persona")
        st.caption("Arquivo ativo:")
        st.code(inspect.getfile(mary_persona.get_persona))
        st.caption("repositories.py ativo:")
        st.code(inspect.getfile(crep.delete_last_interaction))

        if st.button("ðŸ§¾ Listar FATOS (chave_do_usuário_atual)", key="btn_list_facts_now"):
            Reino Unido = _usuario_key_atual()
            st.write("usuario_key:", uk)
            tentar:
                st.json(get_facts(uk) ou {})
            exceto Exception como e:
                st.error(f"Falha ao ler fatos: {type(e).__name__}: {e}")

        if st.button("â™»ï¸ Recarregar persona AGORA", key="btn_reload_persona"):
            importlib.reload(mary_persona)
            import characters.mary.service as mary_service
            importlib.reload(mary_service)

            _matar_todos_os_serviços_da_Maria()
            st.session_state["mary_intro_done"] = False
            st.session_state["chat_history"] = []
            _invalidate_backend_cache()
            _limpar_caches_de_todos_os_relacionados_da_mary()
            st.session_state["mary_timeline_locked"] = False
            st.session_state["mary_rel_meta_last"] = None
            st.success("Pessoa + Serviço recarregados. Contexto reinjetado.")
            st.rerun()

        # ======================================================
        # ðŸ§ MEMÓRIAS PERMANENTES (compartilhado)
        # ======================================================
        st.markdown("---")
        st.subheader("ðŸ§ Memórias permanentes (compartilhadas)")

        shared_key = _shared_key_atual()
        st.caption("Chave compartilhada:")
        st.code(chave_compartilhada)

        if st.button("ðŸ“œ Listar memórias", key="btn_list_mems"):
            st.session_state["__mem_list"] = list_memories(shared_key, limit=200) or []

        if st.button("ðŸ§½ Apagar última memória", key="btn_delete_last_mem"):
            ok = excluir_última_memória(chave_compartilhada)
            st.success("âœ… última memória apagada." if ok else "Nada para apagar.")
            st.session_state["__mem_list"] = list_memories(shared_key, limit=200) or []
            _limpar_caches_de_todos_os_relacionados_da_mary()
            st.rerun()

        if st.button("ðŸ'£ Apagar TODAS as memórias", key="btn_delete_all_mems"):
            n = excluir_todas_as_memórias(chave_compartilhada)
            st.success(f"âœ… Apaguei {n} memórias.")
            st.session_state["__mem_list"] = []
            _limpar_caches_de_todos_os_relacionados_da_mary()
            st.rerun()

        mems_view = st.session_state.get("__mem_list")
        se mems_view não for None:
            st.json(mems_view)

        # ======================================================
        # ðŸ—ƒï¸ MEMÓRIA LONGA (DB) — 1 documento por memória + Pesquisa de texto
        # ======================================================
        st.markdown("---")
        st.subheader("ðŸ—ƒï¸ Memória Longa (DB) — Pesquisa de Texto")

        lm_userkey = _shared_key_atual()
        st.caption("Chave usada na Long Memory:")
        st.code(lm_userkey)

        col1, col2 = st.columns([1, 1])
        com col1:
            if st.button("ðŸ§± Criar índices de memória longa (Mongo)", key="btn_lm_indexes"):
                tentar:
                    garantir_índices_de_memória_longa()
                    st.success("âœ… Índices de long_memory garantidos (se backend=mongo).")
                exceto Exception como e:
                    st.error(f"Falha ao criar índices: {type(e).__name__}: {e}")

        com col2:
            if st.button("ðŸ“š Listar últimos 50 (DB)", key="btn_lm_list"):
                tentar:
                    st.session_state["__lm_list"] = list_long_memory(lm_userkey, limit=50) or []
                exceto Exception como e:
                    st.error(f"Falha ao listar: {type(e).__name__}: {e}")
                    st.session_state["__lm_list"] = []

        col3, col4 = st.columns(2)

        com col3:
            if st.button("ðŸ§½ Apagar Última (DB)", key="btn_lm_delete_last"):
                tentar:
                    ok = delete_last_long_memory(lm_userkey)
                    Se estiver tudo bem:
                        st.success("âœ… última memória (DB) apagada.")
                    outro:
                        st.info("Nada para apagar (DB).")
                    st.session_state["__lm_list"] = list_long_memory(lm_userkey, limit=50) or []
                exceto Exception como e:
                    st.error(f"Falha ao apagar última (DB): {type(e).__name__}: {e}")
                st.rerun()

        com col4:
            confirm_all = st.checkbox("Confirmo excluir TODAS (DB)", key="lm_confirm_delete_all")
            if st.button("ðŸ'£ Apagar TODAS (DB)", key="btn_lm_delete_all", disabled=not confirm_all):
                tentar:
                    n = delete_all_long_memory(lm_userkey)
                    st.success(f"âœ… Apaguei {n} memórias (DB).")
                    st.session_state["__lm_list"] = []
                    st.session_state["__lm_search"] = []
                    st.session_state["lm_confirm_delete_all"] = False
                exceto Exception como e:
                    st.error(f"Falha ao apagar todas (DB): {type(e).__name__}: {e}")
                st.rerun()

        st.markdown("### âž• Inserir memória (DB)")
        lm_text = st.text_area("Texto da memória", key="lm_text_area", height=90, placeholder="Ex: Mary odeia amendoim #500...")
        lm_title = st.text_input("Título (opcional)", key="lm_title_inp", value="")
        lm_kind = st.text_input("tipo (opcional)", key="lm_kind_inp", value="memória")

        if st.button("ðŸ'¾ Salvar na long_memory", key="btn_lm_save"):
            tentar:
                meta = {
                    "tipo": (lm_kind ou "memória").strip(),
                    "título": (lm_title ou "").strip(),
                    "timeline_at_save": _timeline(),
                    "user_id": str(st.session_state.get("user_id", "Janio Donisete")),
                    "fonte": "ui_long_memory",
                }
                doc = append_long_memory(lm_userkey, lm_text, meta=meta)
                st.success(f"âœ… Gravado: id={doc.get('id')} ts={doc.get('ts')}")
            exceto Exception como e:
                st.error(f"Falha ao gravar: {type(e).__name__}: {e}")

        st.markdown("### ðŸ”Ž Buscar (Mongo $text)")
        q = st.text_input("Consulta", key="lm_q_inp", value="", placeholder="Ex: amendoim 500")
        lim = st.slider("Limite de resultados", min_value=5, max_value=50, value=20, step=5, key="lm_lim_slider")

        if st.button("ðŸ” Buscar agora", key="btn_lm_search"):
            tentar:
                st.session_state["__lm_search"] = search_long_memory_text(lm_userkey, q, limit=int(lim)) or []
            exceto Exception como e:
                st.error(f"Falha na busca: {type(e).__name__}: {e}")
                st.session_state["__lm_search"] = []

        se st.session_state.get("__lm_search") não for None:
            st.caption("Resultados da busca:")
            st.json(st.session_state.get("__lm_search") ou [])

        se st.session_state.get("__lm_list") não for None:
            st.caption("Últimas memórias (DB):")
            st.json(st.session_state.get("__lm_list") ou [])

    # ===== BOOT =====
    _boot_visual_if_empty()

    # ===== RENDERIZAR =====
    hist = st.session_state.get("chat_history", [])
    limite_visual = int(st.session_state.get("limite_visual", DEFAULT_VISUAL_LIMIT))
    visível = hist[-limite_visual:] se len(hist) > limite_visual senão hist

    Para a função, o conteúdo deve estar visível:
        com st.chat_message(role):
            se a função for "assistente":
                st.markdown(_format_paragraphs(content))
            outro:
                st.markdown(conteúdo)

    mensagens_mostradas = len(visível)
    total_msgs = len(hist)
    interações_mostradas = soma(1 para r, _ em visível se r == "usuário")
    total_interações = soma(1 para r, _ em hist se r == "usuário")
    st.caption(
        f"ðŸ“Œ Mostrando {shown_interactions} interações ({shown_msgs} mensagens) — "
        f"Total no capítulo: {total_interactions} interações ({total_msgs} mensagens)."
    )

    # ===== ENTRADA =====
    prompt = st.chat_input("Fala algo pra Mary... (Shift+Enter quebra linha)")
    se solicitado:
        se não st.session_state["mary_timeline_locked"]:
            st.session_state["mary_timeline_locked"] = True

        agora = tempo.tempo()
        last_ts = float(st.session_state.get("last_submit_ts", 0.0))
        último_txt = str(st.session_state.get("último_texto_enviado", ""))

        se prompt.strip() == last_txt.strip() e (agora - last_ts) < 1.2:
            st.warning("âš ï¸ Mensagem repetida muito rápida. Ignorando para evitar duplicação.")
            st.stop()

        st.session_state["last_submit_ts"] = agora
        st.session_state["last_submit_text"] = prompt

        st.session_state["chat_history"].append(("user", prompt))
        com st.chat_message("user"):
            st.markdown(prompt)

        svc = _get_service()
        tl_ativo = _linha do tempo()
        nsfw_active = bool(st.session_state.get("mary_nsfw_on", False))

        tentar:
            resposta = svc.reply(
                usuário=st.session_state.get("user_id", "Janio Donisete"),
                model=st.session_state.get("model") ou DEFAULT_MODEL,
                prompt=prompt,
                linha do tempo=tl_ativo,
                nsfw=nsfw_ativo,
            )

        exceto RuntimeError como e:
            msg = str(e)
            if "modelo retornou vazio" em msg.lower():
                st.warning("âš ï¸ O modelo retornou vazio. Troque o modelo na barra lateral ou verifique o provedor.")
                svc_err = getattr(svc, "last_error", None)
                último_erro = st.session_state.get("último_erro_do_modelo")
                se svc_err ou last_err:
                    st.caption("Detalhe técnico (diagnóstico):")
                    se svc_err:
                        st.code(str(svc_err))
                    se last_err e last_err != svc_err:
                        st.code(str(último_erro))
                st.stop()
            elevação

        exceto Exception como e:
            st.error(f"ðŸ'¥ Erro real ao chamar o modelo: {type(e).__name__}: {e}")
            st.code(traceback.format_exc())
            st.stop()

        com st.chat_message("assistant"):
            st.markdown(_format_paragraphs(resposta))

        st.session_state["chat_history"].append(("assistant", resposta))
        _invalidate_backend_cache()
        st.rerun()


se __name__ == "__main__":
    principal()