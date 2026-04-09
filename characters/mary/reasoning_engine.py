from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple


STOPWORDS_PT = {
    "a", "o", "os", "as", "um", "uma", "uns", "umas",
    "de", "do", "da", "dos", "das",
    "em", "no", "na", "nos", "nas",
    "por", "para", "pra", "pro",
    "com", "sem",
    "que", "e", "ou", "mas", "se", "como", "quando", "onde", "porque", "pq",
    "eu", "tu", "ele", "ela", "nós", "nos", "gente", "você", "voce", "vc",
    "meu", "minha", "meus", "minhas", "teu", "tua", "teus", "tuas", "seu", "sua", "seus", "suas",
    "isso", "esse", "essa", "isto", "aquilo",
    "aqui", "ali", "lá", "la",
    "agora", "hoje", "ontem", "amanhã", "amanha",
    "mesmo", "assim", "tipo", "sabe",
    "vai", "vem", "vamos", "vou", "quer", "quero",
    "está", "esta", "estou", "tá", "ta", "tô", "to",
    "foi", "era", "ser", "ter", "tem", "tinha",
    "já", "ja", "ainda", "mais", "menos",
    "não", "nao", "sim",
}

SCENE_VERBS = {
    "correr", "correndo", "corre", "corri", "treinar", "treino", "treinando",
    "andar", "andando", "caminhar", "caminhando",
    "beber", "bebendo", "tomar", "tomando", "pedir", "pedindo",
    "sentar", "sentando", "parar", "parando",
    "entrar", "entrando", "ir", "indo", "chegar", "chegando",
    "conversar", "falando", "dizer", "dizendo",
    "beijar", "beijando", "tocar", "tocando",
    "olhar", "olhando", "aproximar", "aproximando",
}

PLACE_HINTS = {
    "praia", "orla", "calçadão", "calcadao", "quiosque", "bar", "clube",
    "hotel", "quarto", "carro", "academia", "banheiro", "chuveiro",
    "restaurante", "casa", "apartamento", "cozinha", "sala", "píer", "pier",
}

GENERIC_OBJECT_WORDS = {
    "água", "agua", "coco", "drink", "bebida", "cerveja", "vinho", "suco",
    "garrafa", "taça", "taca", "copo", "chave", "celular", "bolsa",
    "carta", "toalha", "roupa", "top", "legging", "sapato", "tenis", "tênis",
    "banco", "mesa", "cadeira", "ducha", "chuveiro",
}


def _norm(x: Any) -> str:
    return str(x or "").strip().lower()


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text or "")
        if unicodedata.category(c) != "Mn"
    )


def _norm_soft(x: Any) -> str:
    return _strip_accents(_norm(x))


def _has_any(text: str, terms: List[str]) -> bool:
    return any(t in text for t in terms)


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _score_has_any(text: str, terms: List[str], weight: float) -> float:
    return weight if _has_any(text, terms) else 0.0


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _tokenize(text: str) -> List[str]:
    txt = _norm_soft(text)
    return re.findall(r"[a-zA-Zà-ÿÀ-Ÿ0-9]+", txt, flags=re.UNICODE)


def _extract_names(raw_text: str) -> List[str]:
    names = re.findall(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+\b", str(raw_text or ""))
    out: List[str] = []
    for n in names:
        nl = _norm_soft(n)
        if nl in {"mary", "janio"}:
            continue
        out.append(n.strip())
    return out


def _extract_candidate_phrases(raw_text: str) -> List[str]:
    """
    Extrai candidatos genéricos de 1 a 3 palavras,
    sem depender de lista fixa de exemplos.
    """
    tokens = _tokenize(raw_text)
    tokens = [t for t in tokens if len(t) >= 3 and t not in STOPWORDS_PT]

    phrases: List[str] = []

    # unigramas
    for t in tokens:
        phrases.append(t)

    # bigramas e trigramas simples
    for i in range(len(tokens) - 1):
        a, b = tokens[i], tokens[i + 1]
        if a not in STOPWORDS_PT and b not in STOPWORDS_PT:
            phrases.append(f"{a} {b}")

    for i in range(len(tokens) - 2):
        a, b, c = tokens[i], tokens[i + 1], tokens[i + 2]
        if a not in STOPWORDS_PT and b not in STOPWORDS_PT and c not in STOPWORDS_PT:
            phrases.append(f"{a} {b} {c}")

    return phrases


def _rank_salient_terms(
    recent_turns: Optional[List[Dict[str, str]]],
    facts: Dict[str, Any],
    scene_state: Dict[str, Any],
) -> Counter:
    """
    Ranqueia termos salientes com peso por recência, repetição e alinhamento com facts/cena.
    """
    counter: Counter = Counter()
    turns = recent_turns or []

    # peso por recência: últimos turnos valem mais
    for idx, turn in enumerate(turns[-5:]):
        weight = 1 + idx  # o mais recente recebe mais peso
        combined = (
            str(turn.get("user") or "").strip()
            + " "
            + str(turn.get("mary") or "").strip()
        ).strip()

        for name in _extract_names(combined):
            counter[name] += 3.0 * weight

        for phrase in _extract_candidate_phrases(combined):
            # evita inflar demais termos inúteis
            if phrase in STOPWORDS_PT:
                continue
            counter[phrase] += 1.0 * weight

    # boost de alinhamento com facts
    assunto = str(facts.get("state.assunto") or "").strip()
    local = str(scene_state.get("local") or facts.get("cena.local") or "").strip()

    for phrase in _extract_candidate_phrases(assunto):
        counter[phrase] += 2.0

    for phrase in _extract_candidate_phrases(local):
        counter[phrase] += 2.5

    return counter


def _infer_interlocutor(
    recent_turns: Optional[List[Dict[str, str]]],
    facts: Dict[str, Any],
) -> str:
    # 1) facts já vencem
    fact_interlocutor = str(facts.get("scene.interlocutor") or "").strip()
    if fact_interlocutor:
        return fact_interlocutor

    # 2) último nome próprio relevante das últimas interações
    turns = recent_turns or []
    names: List[str] = []
    for t in turns[-5:]:
        combined = (
            str(t.get("user") or "").strip()
            + " "
            + str(t.get("mary") or "").strip()
        ).strip()
        names.extend(_extract_names(combined))

    filtered = [n for n in names if _norm_soft(n) not in {"mary", "janio"}]
    if filtered:
        return filtered[-1]

    # 3) vocativos genéricos
    joined = " ".join(
        (
            str(t.get("user") or "").strip()
            + " "
            + str(t.get("mary") or "").strip()
        ).strip()
        for t in turns[-5:]
    )
    joined_n = _norm_soft(joined)
    if "amiga" in joined_n:
        return "amiga"
    if "amigo" in joined_n:
        return "amigo"

    return ""


def _infer_local_ativo(
    recent_turns: Optional[List[Dict[str, str]]],
    facts: Dict[str, Any],
    scene_state: Dict[str, Any],
) -> str:
    local = str(scene_state.get("local") or facts.get("cena.local") or facts.get("state.local") or "").strip()
    if local:
        return local

    joined = " ".join(
        (
            str(t.get("user") or "").strip()
            + " "
            + str(t.get("mary") or "").strip()
        ).strip()
        for t in (recent_turns or [])[-5:]
    )
    joined_n = _norm_soft(joined)

    for place in PLACE_HINTS:
        if _norm_soft(place) in joined_n:
            return place

    return ""


def _infer_objeto_ativo(
    recent_turns: Optional[List[Dict[str, str]]],
    facts: Dict[str, Any],
    scene_state: Dict[str, Any],
) -> str:
    """
    Detecção genérica de objeto ativo por saliência semântica,
    sem lista fixa de exemplos específicos.
    """
    counter = _rank_salient_terms(recent_turns, facts, scene_state)
    if not counter:
        return ""

    candidates: List[Tuple[str, float]] = []
    for term, score in counter.items():
        t = _norm_soft(term)

        # ignora ruído estrutural
        if t in STOPWORDS_PT:
            continue
        if len(t) < 3:
            continue

        # aceita nomes compostos e palavras com cara de objeto/lugar concreto
        looks_concrete = (
            " " in t
            or t in GENERIC_OBJECT_WORDS
            or any(h in t for h in PLACE_HINTS)
        )

        if looks_concrete:
            candidates.append((term, float(score)))

    if not candidates:
        # fallback: primeiro termo saliente não banal
        for term, score in counter.most_common(20):
            t = _norm_soft(term)
            if t not in STOPWORDS_PT and len(t) >= 4:
                return term
        return ""

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]


def _infer_acao_em_andamento(
    user_text: str,
    recent_turns: Optional[List[Dict[str, str]]],
    scene_state: Dict[str, Any],
    facts: Dict[str, Any],
) -> str:
    action = str(scene_state.get("acao") or facts.get("cena.acao") or "").strip()
    if action and _norm_soft(action) not in {"em andamento", "transicao", "transição"}:
        return action

    joined = (
        str(user_text or "").strip()
        + " "
        + " ".join(
            (
                str(t.get("user") or "").strip()
                + " "
                + str(t.get("mary") or "").strip()
            ).strip()
            for t in (recent_turns or [])[-5:]
        )
    ).strip()

    tokens = _tokenize(joined)
    for tk in tokens:
        if tk in SCENE_VERBS:
            return tk

    assunto = str(facts.get("state.assunto") or "").strip()
    if assunto:
        return assunto

    return ""


def _infer_continuidade(
    recent_turns: Optional[List[Dict[str, str]]],
    objeto_ativo: str,
    interlocutor: str,
    local_ativo: str,
    acao_em_andamento: str,
) -> Dict[str, str]:
    turns = recent_turns or []
    last_turn = turns[-1] if turns else {}

    last_user = str(last_turn.get("user") or "").strip()
    last_mary = str(last_turn.get("mary") or "").strip()

    ultima_acao = last_user or last_mary

    continuidade_imediata = ""
    if last_mary:
        continuidade_imediata = last_mary
    elif last_user:
        continuidade_imediata = last_user

    chunks: List[str] = []

    if acao_em_andamento:
        chunks.append(f"a ação ainda gira em torno de {acao_em_andamento}")
    if objeto_ativo:
        chunks.append(f"o objeto ativo da cena é {objeto_ativo}")
    if interlocutor:
        chunks.append(f"Mary continua interagindo com {interlocutor}")
    if local_ativo:
        chunks.append(f"a cena permanece em {local_ativo}")

    proximo_passo_plausivel = ", ".join(chunks).strip()
    if not proximo_passo_plausivel:
        proximo_passo_plausivel = "continuar a cena do ponto em que ela parou, sem trocar objeto, local ou interlocutor"

    return {
        "ultima_acao": ultima_acao,
        "continuidade_imediata": continuidade_imediata,
        "proximo_passo_plausivel": proximo_passo_plausivel,
    }


def build_internal_reasoning(
    *,
    user_text: str,
    facts: Dict[str, Any],
    memories: List[str],
    scene_state: Dict[str, Any],
    recent_turns: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Reasoning híbrido:
    1) lê sinais do turno
    2) calcula scores internos
    3) aplica regras duras
    4) decide direção narrativa
    5) resume continuidade imediata das últimas 5 interações
    """
    t = _norm(user_text)
    facts = facts if isinstance(facts, dict) else {}
    scene_state = scene_state if isinstance(scene_state, dict) else {}

    locked = bool(scene_state.get("locked"))
    intimacy_phase = _safe_int(facts.get("intimacy.phase", 0), 0)
    jealousy_level = _safe_int(facts.get("rel.jealousy_level", 0), 0)

    rel_state = facts.get("rel") if isinstance(facts.get("rel"), dict) else {}
    if not isinstance(rel_state, dict):
        rel_state = {}

    # --------------------------------------------------
    # Memória útil
    # --------------------------------------------------
    memory_hint = memories[-1] if memories else ""
    mem_text = _norm(" ".join(memories[-3:])) if memories else ""

    # --------------------------------------------------
    # Continuidade semântica genérica
    # --------------------------------------------------
    interlocutor = _infer_interlocutor(recent_turns, facts)
    local_ativo = _infer_local_ativo(recent_turns, facts, scene_state)
    objeto_ativo = _infer_objeto_ativo(recent_turns, facts, scene_state)
    acao_em_andamento = _infer_acao_em_andamento(user_text, recent_turns, scene_state, facts)

    continuity = _infer_continuidade(
        recent_turns=recent_turns,
        objeto_ativo=objeto_ativo,
        interlocutor=interlocutor,
        local_ativo=local_ativo,
        acao_em_andamento=acao_em_andamento,
    )

    ultima_acao = continuity["ultima_acao"]
    continuidade_imediata = continuity["continuidade_imediata"]
    proximo_passo_plausivel = continuity["proximo_passo_plausivel"]

    # --------------------------------------------------
    # Scores base
    # --------------------------------------------------
    desire_score = 0.10
    risk_score = 0.10
    guilt_score = 0.10
    attachment_score = 0.20
    pressure_score = 0.00

    desire_score += _score_has_any(
        t,
        ["amor", "beijo", "me beija", "fica comigo", "vem cá", "abraço", "carinho", "quero você", "te desejo"],
        0.30,
    )
    attachment_score += _score_has_any(
        t,
        ["amor", "fica comigo", "carinho", "abraço", "quero você"],
        0.35,
    )

    desire_score += _score_has_any(
        t,
        ["me toca", "chega perto", "não para", "nao para", "encosta", "vem mais", "quero sentir"],
        0.25,
    )

    risk_score += _score_has_any(
        t,
        ["outro homem", "encontro", "trair", "sozinho comigo", "escondido"],
        0.55,
    )
    guilt_score += _score_has_any(
        t,
        ["trair", "escondido", "sozinho comigo"],
        0.45,
    )

    pressure_score += _score_has_any(
        t,
        ["agora", "vai", "faz logo", "sem pensar", "anda", "decide logo", "não enrola", "nao enrola"],
        0.65,
    )

    if jealousy_level >= 1:
        attachment_score += 0.10
        guilt_score += 0.08

    if jealousy_level >= 2:
        attachment_score += 0.12
        risk_score += 0.12

    if intimacy_phase >= 1:
        desire_score += 0.08
    if intimacy_phase >= 2:
        desire_score += 0.12
    if intimacy_phase >= 3:
        desire_score += 0.10
    if intimacy_phase >= 4:
        desire_score += 0.08

    if mem_text:
        if _has_any(mem_text, ["ciúme", "ciume", "risco", "culpa", "segredo"]):
            guilt_score += 0.06
            risk_score += 0.06

        if _has_any(mem_text, ["carinho", "beijo", "abraço", "abraco", "desejo", "saudade"]):
            desire_score += 0.08
            attachment_score += 0.08

    if continuidade_imediata:
        attachment_score += 0.03

    if locked:
        risk_score += 0.08

    desire_score = _clip01(desire_score)
    risk_score = _clip01(risk_score)
    guilt_score = _clip01(guilt_score)
    attachment_score = _clip01(attachment_score)
    pressure_score = _clip01(pressure_score)

    # --------------------------------------------------
    # Defaults narrativos
    # --------------------------------------------------
    intent = "neutra"
    emotion = "estavel"
    subtext = "nenhum"
    pace = "normal"
    tension = "media"
    rules: List[str] = []
    decision = "responder"
    narrative_goal = "manter_fluxo"
    delivery_mode = "fala_com_subtexto"
    advance_limit = "leve"

    # --------------------------------------------------
    # Regras duras
    # --------------------------------------------------
    if locked:
        rules.append("nao_mudar_cena")
        rules.append("nao_avancar_tempo")

    if risk_score >= 0.60:
        rules.append("nao_concluir_ato")
        rules.append("manter_ambiguidade")

    if intimacy_phase >= 4:
        rules.append("permitir_climax_se_usuario_sinalizar")

    if objeto_ativo:
        rules.append("nao_substituir_objeto_ativo")

    if interlocutor:
        rules.append("manter_interlocutor_atual")

    if local_ativo:
        rules.append("manter_local_ativo")

    # --------------------------------------------------
    # Decisão principal
    # --------------------------------------------------
    if pressure_score >= 0.60:
        intent = "resistir"
        emotion = "tensa"
        subtext = "nao_quero_ser_empurrada"
        pace = "curto"
        tension = "alta"
        decision = "recuar_com_presenca"
        narrative_goal = "retomar_controle"
        delivery_mode = "fala_direta"
        advance_limit = "minimo"

    elif risk_score >= 0.55 or guilt_score >= 0.55:
        intent = "conflito"
        emotion = "dividida"
        subtext = "curiosidade_reprimida"
        pace = "lento"
        tension = "alta"

        if attachment_score >= 0.45 or jealousy_level >= 2:
            decision = "resistir"
            emotion = "alerta"
            narrative_goal = "proteger_vinculo"
            delivery_mode = "fala_direta"
            advance_limit = "minimo"
        else:
            decision = "hesitar"
            narrative_goal = "prolongar_tensao"
            delivery_mode = "fala_com_subtexto"
            advance_limit = "minimo"

    elif desire_score >= 0.45 and attachment_score >= 0.40:
        intent = "aproximar"
        emotion = "envolvida"
        subtext = "desejo_com_vinculo"
        pace = "lento"
        tension = "media"
        decision = "acolher"
        narrative_goal = "aprofundar_conexao"
        delivery_mode = "fala_direta"
        advance_limit = "medio"

    elif desire_score >= 0.50 and intimacy_phase >= 2:
        intent = "ceder_com_controle"
        emotion = "acesa"
        subtext = "entrega_progressiva"
        pace = "normal"
        tension = "alta"
        decision = "provocar"
        narrative_goal = "escalar_sem_finalizar"
        delivery_mode = "micro_acao"
        advance_limit = "medio"

    elif memory_hint:
        intent = "lembrar"
        emotion = "sensivel"
        subtext = "eco_de_memoria"
        pace = "lento"
        tension = "media"
        decision = "responder"
        narrative_goal = "manter_fluxo"
        delivery_mode = "fala_com_subtexto"
        advance_limit = "leve"

    if intimacy_phase >= 4 and decision in ("acolher", "provocar"):
        narrative_goal = "sustentar_pico"

    if locked and decision == "provocar" and risk_score >= 0.50:
        delivery_mode = "fala_com_subtexto"
        advance_limit = "leve"

    if proximo_passo_plausivel and narrative_goal == "manter_fluxo":
        narrative_goal = "continuar_cena_com_coerencia"

    return {
        "intent": intent,
        "emotion": emotion,
        "subtext": subtext,
        "pace": pace,
        "tension": tension,
        "rules": rules,
        "decision": decision,
        "narrative_goal": narrative_goal,
        "delivery_mode": delivery_mode,
        "advance_limit": advance_limit,
        "memory_hint": memory_hint,
        "interlocutor": interlocutor,
        "objeto_ativo": objeto_ativo,
        "local_ativo": local_ativo,
        "acao_em_andamento": acao_em_andamento,
        "ultima_acao": ultima_acao,
        "continuidade_imediata": continuidade_imediata,
        "proximo_passo_plausivel": proximo_passo_plausivel,
        "scores": {
            "desire": round(desire_score, 3),
            "risk": round(risk_score, 3),
            "guilt": round(guilt_score, 3),
            "attachment": round(attachment_score, 3),
            "pressure": round(pressure_score, 3),
        },
    }
