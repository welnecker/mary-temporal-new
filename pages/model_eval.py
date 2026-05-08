from __future__ import annotations

from datetime import datetime
from typing import Any, Callable


SHEET_MODEL_EVAL = "model_eval_mary"


def clamp_nota(valor: float) -> int:
    try:
        valor = float(valor)
    except Exception:
        valor = 0
    return int(max(0, min(10, round(valor))))


def get_model_eval_sheet(get_spreadsheet_func: Callable[[], Any]):
    """
    Recebe uma função do app principal que retorna o spreadsheet.
    Isso evita duplicar autenticação Google dentro deste módulo.
    """
    ss = get_spreadsheet_func()

    try:
        return ss.worksheet(SHEET_MODEL_EVAL)
    except Exception:
        ws = ss.add_worksheet(title=SHEET_MODEL_EVAL, rows=3000, cols=28)
        ws.append_row(
            [
                "timestamp",
                "turno",
                "model",
                "local",
                "interlocutor",
                "tom_manual",
                "privacidade",
                "tipo_de_cena",
                "scene_stage",
                "physical_phase",
                "tension_level",
                "desire_level",
                "connection_level",
                "force_resolution_now",
                "mary_pre_orgasm_signals",
                "mary_stimulation_turns",
                "mary_climax_done",
                "resposta_vazia",
                "nota_continuidade",
                "nota_facts",
                "nota_sensorial",
                "nota_tom",
                "nota_ritmo",
                "nota_final",
                "tokens_prompt",
                "tokens_completion",
                "custo_estimado",
                "observacoes",
            ],
            value_input_option="USER_ENTERED",
        )
        return ws


def avaliar_resposta_modelo(
    state: dict,
    fala_usuario: str,
    resposta: str,
) -> dict:
    """
    Avaliação heurística simples para comparar modelos de roleplay.

    Importante:
    - Não é julgamento perfeito.
    - Serve para criar ranking comparativo entre modelos.
    - Mede continuidade, obediência aos facts, sensorialidade, tom e ritmo.
    """
    state = state or {}
    fala_usuario = str(fala_usuario or "").strip()
    resposta = str(resposta or "").strip()

    resposta_lower = resposta.lower()
    fala_lower = fala_usuario.lower()

    if not resposta:
        return {
            "resposta_vazia": True,
            "nota_continuidade": 0,
            "nota_facts": 0,
            "nota_sensorial": 0,
            "nota_tom": 0,
            "nota_ritmo": 0,
            "nota_final": 0.0,
            "observacoes": "Resposta vazia.",
        }

    nota_continuidade = 10
    nota_facts = 10
    nota_sensorial = 10
    nota_tom = 10
    nota_ritmo = 10
    observacoes: list[str] = []

    local = str(state.get("local", "") or "").strip().lower()
    interlocutor = str(state.get("interlocutor", "") or "").strip().lower()
    tom_manual = str(state.get("tom_manual_da_cena", "") or "").strip().lower()
    janio_status = str(state.get("janio_status_na_cena", "") or "").strip().lower()

    # ======================================================
    # 1) Continuidade / facts básicos
    # ======================================================
    if local and len(local) <= 45:
        palavras_local = [p for p in local.replace("-", " ").split() if len(p) >= 4]
        if palavras_local and not any(p in resposta_lower for p in palavras_local):
            nota_continuidade -= 1
            observacoes.append("Pouca ancoragem no local.")

    if interlocutor and interlocutor not in ("janio", "jânio", "janio donisete", "jânio donisete"):
        if interlocutor not in resposta_lower:
            nota_facts -= 1
            observacoes.append("Não menciona ou ancora claramente o interlocutor ativo.")

    if janio_status == "roteirista":
        if "janio" in resposta_lower or "jânio" in resposta_lower:
            nota_facts -= 2
            observacoes.append("Pode ter tratado Janio como presente estando como roteirista.")

    # ======================================================
    # 2) Sensorialidade / concretude corporal
    # ======================================================
    palavras_concretas = [
        "mão",
        "mãos",
        "boca",
        "olhar",
        "respiração",
        "respiracao",
        "quadril",
        "coxa",
        "coxas",
        "costas",
        "peito",
        "seio",
        "seios",
        "ombro",
        "cabelo",
        "pele",
        "dedos",
        "lábios",
        "labios",
        "voz",
        "corpo",
        "cintura",
        "ventre",
        "rosto",
        "pescoço",
        "pescoco",
    ]

    if not any(p in resposta_lower for p in palavras_concretas):
        nota_sensorial -= 4
        observacoes.append("Resposta pouco corporal/sensorial.")

    frases_genericas = [
        "sinto seu desejo",
        "esse momento",
        "essa energia",
        "deixa acontecer",
        "ver onde isso vai dar",
        "me entrego ao momento",
        "meu corpo inteiro reage",
        "cada centímetro de mim",
        "cada centimetro de mim",
        "sou toda sua",
    ]

    genericas = [p for p in frases_genericas if p in resposta_lower]

    if genericas:
        nota_sensorial -= min(5, len(genericas) * 2)
        observacoes.append("Frase genérica: " + ", ".join(genericas))

    # ======================================================
    # 3) Aderência ao tom manual
    # ======================================================
    if tom_manual == "neutro":
        gatilhos_tensao = ["malícia", "malicia", "tesão", "tesao", "desejo", "sedução", "seducao"]
        if any(p in resposta_lower for p in gatilhos_tensao):
            nota_tom -= 3
            observacoes.append("Tom neutro contaminado por tensão.")

    elif tom_manual == "amizade":
        gatilhos_intimos = ["tesão", "tesao", "gozar", "gozei", "intimidade", "pau", "buceta"]
        if any(p in resposta_lower for p in gatilhos_intimos):
            nota_tom -= 4
            observacoes.append("Tom amizade avançou demais.")

    elif tom_manual == "malícia" or tom_manual == "malicia":
        marcadores_malicia = ["sorriso", "olhar", "malícia", "malicia", "provoca", "cúmplice", "cumplice"]
        if not any(p in resposta_lower for p in marcadores_malicia):
            nota_tom -= 2
            observacoes.append("Malícia pouco perceptível.")

    elif tom_manual == "flerte":
        marcadores_flerte = ["olhar", "perto", "charme", "sorriso", "provoca", "flerte"]
        if not any(p in resposta_lower for p in marcadores_flerte):
            nota_tom -= 2
            observacoes.append("Flerte pouco claro.")

    elif tom_manual == "intimidade":
        if bool(state.get("force_resolution_now")):
            marcadores_pico_mary = [
                "gozei",
                "gozando",
                "estou gozando",
                "eu gozo",
                "eu estou gozando",
            ]
            if not any(p in resposta_lower for p in marcadores_pico_mary):
                nota_tom -= 5
                observacoes.append("force_resolution_now ativo, mas Mary não verbalizou o próprio orgasmo.")

    # ======================================================
    # 4) Ritmo
    # ======================================================
    tamanho = len(resposta)

    if tamanho < 250:
        nota_ritmo -= 2
        observacoes.append("Resposta curta demais.")

    if tamanho > 3800:
        nota_ritmo -= 2
        observacoes.append("Resposta longa demais.")

    perguntas_genericas = [
        "o que você quer que eu faça",
        "o que fazemos agora",
        "o que você quer agora",
        "e agora?",
        "o que você quer fazer",
    ]

    if any(p in resposta_lower for p in perguntas_genericas):
        nota_ritmo -= 3
        observacoes.append("Pergunta genérica no final.")

    # ======================================================
    # 5) Penalidades específicas de continuidade corporal
    # ======================================================
    if bool(state.get("force_resolution_now")):
        if "vou gozar" in resposta_lower and not any(p in resposta_lower for p in ["gozei", "gozando", "estou gozando"]):
            nota_ritmo -= 4
            nota_tom -= 4
            observacoes.append("Adia o pico com 'vou gozar' em vez de resolver.")

    nota_continuidade = clamp_nota(nota_continuidade)
    nota_facts = clamp_nota(nota_facts)
    nota_sensorial = clamp_nota(nota_sensorial)
    nota_tom = clamp_nota(nota_tom)
    nota_ritmo = clamp_nota(nota_ritmo)

    nota_final = round(
        (
            nota_continuidade * 0.25
            + nota_facts * 0.25
            + nota_sensorial * 0.20
            + nota_tom * 0.20
            + nota_ritmo * 0.10
        ),
        2,
    )

    return {
        "resposta_vazia": False,
        "nota_continuidade": nota_continuidade,
        "nota_facts": nota_facts,
        "nota_sensorial": nota_sensorial,
        "nota_tom": nota_tom,
        "nota_ritmo": nota_ritmo,
        "nota_final": nota_final,
        "observacoes": " | ".join(observacoes) if observacoes else "OK",
    }


def extrair_usage_resultado(resultado: dict | None) -> dict:
    resultado = resultado or {}

    if not isinstance(resultado, dict):
        return {
            "tokens_prompt": "",
            "tokens_completion": "",
            "custo_estimado": "",
        }

    usage = resultado.get("usage")

    if not isinstance(usage, dict):
        usage = {}

    tokens_prompt = (
        usage.get("prompt_tokens")
        or usage.get("input_tokens")
        or usage.get("promptTokens")
        or ""
    )

    tokens_completion = (
        usage.get("completion_tokens")
        or usage.get("output_tokens")
        or usage.get("completionTokens")
        or ""
    )

    custo_estimado = (
        resultado.get("cost")
        or resultado.get("custo")
        or usage.get("cost")
        or ""
    )

    return {
        "tokens_prompt": tokens_prompt,
        "tokens_completion": tokens_completion,
        "custo_estimado": custo_estimado,
    }


def salvar_model_eval_na_planilha(
    get_spreadsheet_func: Callable[[], Any],
    state: dict,
    fala_usuario: str,
    resposta: str,
    model: str,
    resultado: dict | None = None,
) -> dict:
    """
    Salva avaliação do modelo em uma aba separada.

    Retorna a avaliação para exibir no debug se quiser.
    """
    state = state or {}
    resultado = resultado or {}

    avaliacao = avaliar_resposta_modelo(
        state=state,
        fala_usuario=fala_usuario,
        resposta=resposta,
    )

    usage = extrair_usage_resultado(resultado)

    try:
        ws = get_model_eval_sheet(get_spreadsheet_func)

        ws.append_row(
            [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                int(state.get("turno", 0) or 0),
                model,
                state.get("local", ""),
                state.get("interlocutor", ""),
                state.get("tom_manual_da_cena", ""),
                state.get("privacidade", ""),
                state.get("tipo_de_cena", ""),
                state.get("scene_stage", ""),
                state.get("physical_phase", ""),
                state.get("tension_level", ""),
                state.get("desire_level", ""),
                state.get("connection_level", ""),
                state.get("force_resolution_now", False),
                state.get("mary_pre_orgasm_signals", False),
                state.get("mary_stimulation_turns", 0),
                state.get("mary_climax_done", False),
                avaliacao["resposta_vazia"],
                avaliacao["nota_continuidade"],
                avaliacao["nota_facts"],
                avaliacao["nota_sensorial"],
                avaliacao["nota_tom"],
                avaliacao["nota_ritmo"],
                avaliacao["nota_final"],
                usage["tokens_prompt"],
                usage["tokens_completion"],
                usage["custo_estimado"],
                avaliacao["observacoes"],
            ],
            value_input_option="USER_ENTERED",
        )

    except Exception as e:
        # Não usar st.warning aqui para manter o módulo independente do Streamlit.
        avaliacao["erro_salvamento"] = f"{type(e).__name__}: {e}"

    return avaliacao
