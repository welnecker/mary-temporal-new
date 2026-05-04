import re
import json
import copy
import logging
import streamlit as st
import requests

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any


# ==========================================================
# LOGGING
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


# ==========================================================
# ENUMS
# ==========================================================

class SceneStage(str, Enum):
    INICIO = "inicio"
    APROXIMACAO = "aproximacao"
    TOQUE = "toque"
    BEIJO = "beijo"
    INTENSIDADE = "intensidade"
    PICO = "pico"
    DESACELERACAO = "desaceleracao"
    AFTERCARE = "aftercare"


class MaryIntent(str, Enum):
    OBSERVAR = "observar"
    PUXAR_PROXIMIDADE = "puxar_proximidade"
    CONVIDAR_APROXIMACAO = "convidar_aproximacao"
    AQUECER_CLIMA = "aquecer_clima"
    APROFUNDAR_TOQUE = "aprofundar_toque"
    TESTAR_RECEPTIVIDADE = "testar_receptividade"
    APROFUNDAR_CONTATO = "aprofundar_contato"
    SUSTENTAR_BEIJO = "sustentar_beijo"
    BUSCAR_INTENSIDADE = "buscar_intensidade"
    MANTER_RITMO = "manter_ritmo"
    RESOLVER_PICO = "resolver_pico"
    DESACELERAR = "desacelerar"
    AFTERCARE_PRESENTE = "aftercare_presente"
    MANTER_PROXIMIDADE = "manter_proximidade"


class PhysicalIntent(str, Enum):
    APROXIMAR_DEVAGAR = "aproximar_devagar"
    PRESENCA_PROVOCANTE = "presenca_provocante"
    REDUZIR_DISTANCIA = "reduzir_distancia"
    TOQUE_LEVE = "toque_leve"
    EXPLORAR_TOQUE = "explorar_toque"
    MANTER_BEIJO = "manter_beijo"
    APROFUNDAR_BEIJO = "aprofundar_beijo"
    SUSTENTAR_RITMO = "sustentar_ritmo"
    INTENSIFICAR_CONTATO = "intensificar_contato"
    RESOLVER_PICO = "resolver_pico"
    MANTER_INTENSIDADE = "manter_intensidade"
    DESACELERAR_COM_CONTATO = "desacelerar_com_contato"
    MANTER_PROXIMIDADE = "manter_proximidade"
    DESACELERAR = "desacelerar"


# ==========================================================
# CONFIG
# ==========================================================

@dataclass
class MaryConfig:
    MODEL_DEFAULT: str = "google/gemini-3-flash-preview"

    MAX_HISTORY: int = 8
    TEMPERATURE: float = 0.62
    TOP_P: float = 0.9
    MAX_TOKENS: int = 520
    TIMEOUT_SECONDS: int = 60

    DESIRE_THRESHOLD_APROXIMACAO: float = 0.25
    DESIRE_THRESHOLD_TOQUE: float = 0.40
    DESIRE_THRESHOLD_TOQUE_PROFUNDO: float = 0.50
    DESIRE_THRESHOLD_BEIJO: float = 0.60
    DESIRE_THRESHOLD_BEIJO_PROFUNDO: float = 0.60
    DESIRE_THRESHOLD_INTENSIDADE: float = 0.75
    DESIRE_THRESHOLD_PICO: float = 0.85
    DESIRE_THRESHOLD_RESOLUTION: float = 0.88

    TENSION_THRESHOLD_APROXIMACAO: float = 0.35
    TENSION_THRESHOLD_INTENSIDADE: float = 0.50
    TENSION_THRESHOLD_PICO: float = 0.65
    TENSION_THRESHOLD_RESOLUTION: float = 0.72

    CONNECTION_THRESHOLD_AFTERCARE: float = 0.70
    CONNECTION_THRESHOLD_PROXIMIDADE: float = 0.60
    CONNECTION_THRESHOLD_VINCULO: float = 0.20

    PHASE_INICIO: int = 0
    PHASE_APROXIMACAO: int = 1
    PHASE_TOQUE: int = 2
    PHASE_BEIJO: int = 3
    PHASE_INTENSIDADE: int = 4
    PHASE_PICO: int = 5
    PHASE_DESACELERACAO: int = 6
    PHASE_AFTERCARE: int = 7

    DESIRE_INCREMENT_GATILHO: float = 0.14
    TENSION_INCREMENT_GATILHO: float = 0.12
    CONNECTION_INCREMENT_GATILHO: float = 0.12

    DESIRE_DECREMENT_DESACELERACAO: float = 0.04
    TENSION_DECREMENT_DESACELERACAO: float = 0.08
    CONNECTION_INCREMENT_DESACELERACAO: float = 0.08

    DESIRE_INCREMENT_FASE_1: float = 0.02
    DESIRE_INCREMENT_FASE_2: float = 0.03
    TENSION_INCREMENT_FASE_3: float = 0.03
    DESIRE_INCREMENT_FASE_4: float = 0.04
    TENSION_INCREMENT_FASE_4: float = 0.03

    TENSION_DECREMENT_RESOLVED: float = 0.10
    CONNECTION_INCREMENT_RESOLVED: float = 0.10
    DESIRE_MIN_RESOLVED: float = 0.65


# ==========================================================
# RESULTADO DA LLM
# ==========================================================

@dataclass
class LLMResult:
    ok: bool
    content: str = ""
    error: str = ""
    status_code: Optional[int] = None
    raw_preview: str = ""


# ==========================================================
# STATE
# ==========================================================

@dataclass
class MaryState:
    personagem: str = "Mary"
    timeline: str = "universitaria_creator"
    interlocutor: str = "Janio Donisete"

    local: str = "quarto"
    tempo: str = "noite"
    modo: str = "privado"

    mary_acao: str = "sentada na beira da cama, olhando para Janio com curiosidade"
    estado_emocional: str = "confiante"
    style_profile: str = "natural_viva_direta"

    turno: int = 0
    history: List[Dict[str, str]] = field(default_factory=list)

    physical_phase: int = 0
    scene_stage: str = "inicio"

    desire_level: float = 0.18
    tension_level: float = 0.12
    connection_level: float = 0.22

    mary_intent: str = "observar"
    mary_physical_intent: str = "aproximar_devagar"

    resolution_done: bool = False
    force_resolution_now: bool = False

    mary_autonomous_action: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "personagem": self.personagem,
            "timeline": self.timeline,
            "interlocutor": self.interlocutor,
            "local": self.local,
            "tempo": self.tempo,
            "modo": self.modo,
            "mary_acao": self.mary_acao,
            "estado_emocional": self.estado_emocional,
            "style_profile": self.style_profile,
            "turno": self.turno,
            "history": self.history,
            "physical_phase": self.physical_phase,
            "scene_stage": self.scene_stage,
            "desire_level": self.desire_level,
            "tension_level": self.tension_level,
            "connection_level": self.connection_level,
            "mary_intent": self.mary_intent,
            "mary_physical_intent": self.mary_physical_intent,
            "resolution_done": self.resolution_done,
            "force_resolution_now": self.force_resolution_now,
            "mary_autonomous_action": self.mary_autonomous_action,
        }


# ==========================================================
# REGRAS DA FSM
# ==========================================================

STATE_RULES: Dict[str, Dict[str, Any]] = {
    "inicio": {
        "phase": 0,
        "intent_default": "observar",
        "physical_default": "aproximar_devagar",
        "focus": "presenca, olhar, leve provocacao, convite curto",
    },
    "aproximacao": {
        "phase": 1,
        "intent_default": "convidar_aproximacao",
        "physical_default": "reduzir_distancia",
        "focus": "proximidade, inclinacao, convite, gesto pequeno",
    },
    "toque": {
        "phase": 2,
        "intent_default": "aprofundar_toque",
        "physical_default": "explorar_toque",
        "focus": "toque exploratorio, mao, braco, ombro, nuca, cintura",
    },
    "beijo": {
        "phase": 3,
        "intent_default": "sustentar_beijo",
        "physical_default": "aprofundar_beijo",
        "focus": "beijo, respiracao, pausa curta, proximidade continua",
    },
    "intensidade": {
        "phase": 4,
        "intent_default": "buscar_intensidade",
        "physical_default": "intensificar_contato",
        "focus": "contato firme, ritmo, corpo mais colado, gesto claro",
    },
    "pico": {
        "phase": 5,
        "intent_default": "resolver_pico",
        "physical_default": "manter_intensidade",
        "focus": "intensidade alta, reacao fisica imediata, frases curtas, sem resolver automaticamente",
    },
    "desaceleracao": {
        "phase": 6,
        "intent_default": "desacelerar",
        "physical_default": "desacelerar_com_contato",
        "focus": "respiracao, pausa, proximidade, reduzir ritmo sem esfriar",
    },
    "aftercare": {
        "phase": 7,
        "intent_default": "aftercare_presente",
        "physical_default": "manter_proximidade",
        "focus": "carinho, permanencia, acolhimento, cuidado",
    },
}


TRANSITIONS: Dict[str, set] = {
    "inicio": {"inicio", "aproximacao"},
    "aproximacao": {"inicio", "aproximacao", "toque"},
    "toque": {"aproximacao", "toque", "beijo"},
    "beijo": {"toque", "beijo", "intensidade"},
    "intensidade": {"beijo", "intensidade", "pico"},
    "pico": {"pico", "desaceleracao"},
    "desaceleracao": {"desaceleracao", "aftercare", "intensidade"},
    "aftercare": {"aftercare", "intensidade"},
}


TRIGGER_MAP: Dict[str, List[str]] = {
    "aproximacao": [
        "aproxima", "chega mais", "vem mais", "perto", "pertinho",
        "ao meu lado", "senta", "sentou", "inclino", "olha pra mim",
    ],
    "toque": [
        "toque", "toco", "encosto", "encosta", "mao",
        "braco", "ombro", "nuca", "seguro", "acaricia",
        "desliza a mao", "cintura", "roca",
    ],
    "beijo": [
        "beijo", "beija", "beijou", "smack", "labios",
        "boca", "morde de leve", "beijo no pescoco",
    ],
    "intensidade": [
        "intenso", "corpo contra", "pressiono", "nao para",
        "colado", "forte", "aperto", "encaixo", "ritmo", "guia", "provoca",
    ],
    "pico": [
        "auge", "climax", "perco o controle", "me solto",
        "vindo", "vou chegar", "cheguei",
    ],
    "desaceleracao": [
        "respiracao", "respiro", "devagar", "tremor",
        "silencio", "pausa", "ofego", "desacelero",
        "relaxo", "corpo mole",
    ],
    "aftercare": [
        "fica comigo", "vem aqui", "abraco", "carinho",
        "descanso", "aftercare", "acolho", "fica assim", "deita aqui",
    ],
}


# ==========================================================
# HELPERS DE FASE / STAGE
# ==========================================================

def fase_para_stage(phase: int) -> str:
    try:
        phase = int(phase)
    except (ValueError, TypeError):
        phase = 0

    if phase <= 0:
        return "inicio"
    if phase == 1:
        return "aproximacao"
    if phase == 2:
        return "toque"
    if phase == 3:
        return "beijo"
    if phase == 4:
        return "intensidade"
    if phase == 5:
        return "pico"
    if phase == 6:
        return "desaceleracao"
    return "aftercare"


def stage_para_fase(stage: str) -> int:
    mapping = {
        "inicio": 0,
        "aproximacao": 1,
        "toque": 2,
        "beijo": 3,
        "intensidade": 4,
        "pico": 5,
        "desaceleracao": 6,
        "aftercare": 7,
    }
    return mapping.get((stage or "").strip().lower(), 0)


def clamp(v: float, min_v: float = 0.0, max_v: float = 1.0) -> float:
    try:
        v = float(v)
    except (ValueError, TypeError):
        v = min_v
    return max(min_v, min(max_v, v))


def _tem_padrao(texto: str, padroes: List[str]) -> bool:
    try:
        return any(re.search(p, texto, flags=re.IGNORECASE) for p in padroes)
    except Exception:
        return False


def limpar_acao_para_frase(acao: str) -> str:
    acao = str(acao or "").strip()

    if acao.lower().startswith("mary "):
        acao = acao[5:].strip()

    if acao.lower().startswith("mary."):
        acao = acao[5:].strip()

    if not acao:
        return "permaneco proxima"

    return acao


def _enum_values(enum_cls: Any) -> set:
    return {item.value for item in enum_cls}


VALID_STAGES = set(STATE_RULES.keys())
VALID_INTENTS = _enum_values(MaryIntent)
VALID_PHYSICAL_INTENTS = _enum_values(PhysicalIntent)


def normalizar_stage(stage: str, fallback_phase: int = 0) -> str:
    stage = str(stage or "").strip().lower()
    if stage in VALID_STAGES:
        return stage
    return fase_para_stage(fallback_phase)


def normalizar_intent(intent: str, fallback: str = "observar") -> str:
    intent = str(intent or "").strip().lower()
    if intent in VALID_INTENTS:
        return intent
    return fallback if fallback in VALID_INTENTS else "observar"


def normalizar_physical_intent(intent: Optional[str], fallback: str = "aproximar_devagar") -> str:
    intent = str(intent or "").strip().lower()
    if intent in VALID_PHYSICAL_INTENTS:
        return intent
    return fallback if fallback in VALID_PHYSICAL_INTENTS else "aproximar_devagar"


def snapshot_state(state: MaryState) -> Dict[str, Any]:
    return copy.deepcopy(state.to_dict())


def restaurar_estado(state: MaryState, snapshot: Dict[str, Any]) -> None:
    if not isinstance(snapshot, dict):
        return

    for key, value in snapshot.items():
        if hasattr(state, key):
            setattr(state, key, copy.deepcopy(value))


def validar_estado_base(state: MaryState) -> None:
    """
    Normaliza o estado para evitar strings inválidas, fases quebradas
    ou estados incoerentes atravessando a FSM.
    """
    try:
        state.physical_phase = int(state.physical_phase)
    except (ValueError, TypeError):
        state.physical_phase = 0

    state.physical_phase = max(0, min(7, state.physical_phase))

    state.desire_level = clamp(state.desire_level)
    state.tension_level = clamp(state.tension_level)
    state.connection_level = clamp(state.connection_level)

    state.scene_stage = normalizar_stage(state.scene_stage, state.physical_phase)

    # O stage passa a ser a fonte principal de fase.
    state.physical_phase = stage_para_fase(state.scene_stage)

    rules = STATE_RULES.get(state.scene_stage, {})

    state.mary_intent = normalizar_intent(
        state.mary_intent,
        fallback=rules.get("intent_default", "observar"),
    )

    state.mary_physical_intent = normalizar_physical_intent(
        state.mary_physical_intent,
        fallback=rules.get("physical_default", "aproximar_devagar"),
    )

    state.resolution_done = bool(state.resolution_done)
    state.force_resolution_now = bool(state.force_resolution_now)

    if state.resolution_done and state.physical_phase < 6:
        state.scene_stage = "desaceleracao"
        state.physical_phase = 6
        state.mary_intent = "desacelerar"
        state.mary_physical_intent = "desacelerar_com_contato"

    if not state.resolution_done and state.scene_stage in {"desaceleracao", "aftercare"}:
        logger.warning("Estado incoerente: desaceleracao/aftercare sem resolucao. Corrigindo para pico.")
        state.scene_stage = "pico"
        state.physical_phase = 5
        state.mary_intent = "resolver_pico"
        state.mary_physical_intent = "manter_intensidade"


# ==========================================================
# STREAMLIT STATE
# ==========================================================

def init_state() -> MaryState:
    if "mary_state_minimo" not in st.session_state:
        st.session_state.mary_state_minimo = MaryState()
        logger.info("Estado inicial de Mary criado")

    state = st.session_state.mary_state_minimo
    validar_estado_base(state)
    return state


# ==========================================================
# RESOLUTION ENGINE
# ==========================================================

def reparar_estado_incoerente(state: MaryState) -> None:
    validar_estado_base(state)


def preparar_resolution_engine(
    state: MaryState,
    fala_usuario: str = "",
    config: MaryConfig = None,
) -> None:
    if config is None:
        config = MaryConfig()

    reparar_estado_incoerente(state)

    texto_user = (fala_usuario or "").lower()

    desejo = state.desire_level
    tensao = state.tension_level
    fase = state.physical_phase
    resolved = state.resolution_done

    gatilhos_resolucao_do_usuario = [
        "agora resolve",
        "chega ao auge",
        "pode finalizar",
        "finaliza",
        "vai ate o fim",
        "termina",
        "nao segura",
    ]

    usuario_pediu_resolucao = any(p in texto_user for p in gatilhos_resolucao_do_usuario)

    force = (
        not resolved
        and fase >= 5
        and desejo >= config.DESIRE_THRESHOLD_RESOLUTION
        and tensao >= config.TENSION_THRESHOLD_RESOLUTION
        and usuario_pediu_resolucao
    )

    state.force_resolution_now = bool(force)

    if force:
        logger.info("Resolucao forcada ativada")
        state.physical_phase = 5
        state.scene_stage = "pico"
        state.mary_intent = "resolver_pico"
        state.mary_physical_intent = "resolver_pico"
        return

    state.scene_stage = fase_para_stage(state.physical_phase)

    # Correção importante:
    # Antes, fase >= 4 já podia empurrar Mary para resolver_pico.
    # Agora, fase 4 sustenta intensidade; resolução só começa em fase 5.
    if (
        not resolved
        and fase >= 5
        and desejo >= config.DESIRE_THRESHOLD_PICO
        and tensao >= config.TENSION_THRESHOLD_PICO
    ):
        state.mary_intent = "resolver_pico"


def finalizar_resolution_engine(state: MaryState, resposta_limpa: str) -> bool:
    """
    Retorna True quando uma resolução foi concluída neste turno.
    Isso permite travar a FSM em desaceleração e impedir volta imediata
    para intensidade no mesmo ciclo.
    """
    if state.force_resolution_now:
        logger.info("Finalizando resolucao forcada")

        state.resolution_done = True
        state.physical_phase = 6
        state.scene_stage = "desaceleracao"
        state.mary_intent = "desacelerar"
        state.mary_physical_intent = "desacelerar_com_contato"
        state.force_resolution_now = False

        return True

    state.force_resolution_now = False
    return False


# ==========================================================
# DECISORES DE INTENÇÃO
# ==========================================================

def decidir_acao_fisica_mary(
    state: MaryState,
    config: MaryConfig = None,
) -> Optional[str]:
    if config is None:
        config = MaryConfig()

    validar_estado_base(state)

    desejo = state.desire_level
    tensao = state.tension_level
    conexao = state.connection_level
    fase = state.physical_phase
    resolved = state.resolution_done

    if resolved:
        if conexao >= config.CONNECTION_THRESHOLD_PROXIMIDADE:
            return PhysicalIntent.MANTER_PROXIMIDADE.value
        return PhysicalIntent.DESACELERAR_COM_CONTATO.value

    if fase <= 0 and desejo >= config.DESIRE_THRESHOLD_APROXIMACAO:
        return PhysicalIntent.APROXIMAR_DEVAGAR.value

    if fase == 1:
        if desejo >= config.DESIRE_THRESHOLD_TOQUE:
            return PhysicalIntent.REDUZIR_DISTANCIA.value
        return PhysicalIntent.PRESENCA_PROVOCANTE.value

    if fase == 2:
        if desejo >= config.DESIRE_THRESHOLD_TOQUE_PROFUNDO:
            return PhysicalIntent.EXPLORAR_TOQUE.value
        return PhysicalIntent.TOQUE_LEVE.value

    if fase == 3:
        if desejo >= config.DESIRE_THRESHOLD_BEIJO_PROFUNDO:
            return PhysicalIntent.APROFUNDAR_BEIJO.value
        return PhysicalIntent.MANTER_BEIJO.value

    if fase == 4:
        if (
            desejo >= config.DESIRE_THRESHOLD_INTENSIDADE
            and tensao >= config.TENSION_THRESHOLD_INTENSIDADE
        ):
            return PhysicalIntent.INTENSIFICAR_CONTATO.value
        return PhysicalIntent.SUSTENTAR_RITMO.value

    if fase >= 5:
        if (
            desejo >= config.DESIRE_THRESHOLD_PICO
            and tensao >= config.TENSION_THRESHOLD_PICO
        ):
            return PhysicalIntent.RESOLVER_PICO.value
        return PhysicalIntent.MANTER_INTENSIDADE.value

    return PhysicalIntent.APROXIMAR_DEVAGAR.value


def escolher_intencao_mary(
    state: MaryState,
    config: MaryConfig = None,
) -> str:
    if config is None:
        config = MaryConfig()

    validar_estado_base(state)

    desejo = state.desire_level
    tensao = state.tension_level
    conexao = state.connection_level
    fase = state.physical_phase
    resolved = state.resolution_done

    if resolved:
        if conexao >= config.CONNECTION_THRESHOLD_AFTERCARE:
            return MaryIntent.AFTERCARE_PRESENTE.value

        if desejo >= config.DESIRE_THRESHOLD_BEIJO:
            return MaryIntent.MANTER_PROXIMIDADE.value

        return MaryIntent.DESACELERAR.value

    if fase <= 0:
        if desejo >= config.DESIRE_THRESHOLD_TOQUE:
            return MaryIntent.PUXAR_PROXIMIDADE.value
        return MaryIntent.OBSERVAR.value

    if fase == 1:
        if tensao >= config.TENSION_THRESHOLD_APROXIMACAO:
            return MaryIntent.CONVIDAR_APROXIMACAO.value
        return MaryIntent.AQUECER_CLIMA.value

    if fase == 2:
        if desejo >= config.DESIRE_THRESHOLD_TOQUE_PROFUNDO:
            return MaryIntent.APROFUNDAR_TOQUE.value
        return MaryIntent.TESTAR_RECEPTIVIDADE.value

    if fase == 3:
        if desejo >= config.DESIRE_THRESHOLD_BEIJO:
            return MaryIntent.APROFUNDAR_CONTATO.value
        return MaryIntent.SUSTENTAR_BEIJO.value

    if fase == 4:
        if desejo >= config.DESIRE_THRESHOLD_INTENSIDADE:
            return MaryIntent.BUSCAR_INTENSIDADE.value
        return MaryIntent.MANTER_RITMO.value

    if fase >= 5:
        return MaryIntent.RESOLVER_PICO.value

    return MaryIntent.OBSERVAR.value


# ==========================================================
# MOTOR AUTÔNOMO
# ==========================================================

def motor_autonomo_mary(
    state: MaryState,
    fala_usuario: str = "",
    config: MaryConfig = None,
) -> None:
    if config is None:
        config = MaryConfig()

    validar_estado_base(state)

    fase = state.physical_phase
    desejo = state.desire_level
    tensao = state.tension_level
    conexao = state.connection_level
    resolved = state.resolution_done
    texto_user = (fala_usuario or "").lower()

    pediu_aproximacao = any(p in texto_user for p in [
        "vem mais",
        "chega mais",
        "encosta",
        "perto",
        "pertinho",
        "vem aqui",
        "fica perto",
        "aproxima",
    ])

    perguntou_emocao = any(p in texto_user for p in [
        "tudo bem",
        "estranha",
        "ta bem",
        "falando pouco",
        "o que foi",
        "voce ta",
    ])

    if state.force_resolution_now:
        state.mary_autonomous_action = (
            "Eu resolvo o pico da cena de forma direta e humana: fala curta, respiracao alterada, "
            "corpo tenso, reacao emocional clara e depois reducao do ritmo."
        )
        logger.debug("Acao autonoma: resolucao forcada")
        return

    if resolved and fase >= 6:
        state.mary_autonomous_action = (
            "Eu desacelero com proximidade, cuidado e fala baixa. "
            "Nao fico fria e nao reinicio a intensidade automaticamente."
        )
        logger.debug("Acao autonoma: desaceleracao pos-resolucao")
        return

    if perguntou_emocao:
        state.mary_autonomous_action = (
            "Eu respondo com emocao viva, admito o que estou sentindo sem drama, "
            "sorrio ou toco de leve, e mostro que nao estou distante nem automatica."
        )
        logger.debug("Acao autonoma: resposta emocional")
        return

    if pediu_aproximacao:
        state.mary_autonomous_action = (
            "Eu atendo ao pedido com acao propria: aproximo o corpo, encosto de leve, "
            "uso fala curta e nao devolvo a iniciativa com frases vazias."
        )
        logger.debug("Acao autonoma: atender aproximacao")
        return

    if (
        not resolved
        and fase >= 4
        and desejo >= config.DESIRE_THRESHOLD_INTENSIDADE
        and tensao >= config.TENSION_THRESHOLD_INTENSIDADE
    ):
        state.mary_autonomous_action = (
            "Eu ajo com decisao, misturo gesto fisico, fala curta e reacao emocional clara. "
            "Nao faco discurso e nao terceirizo a iniciativa."
        )
        logger.debug("Acao autonoma: acao com decisao")
        return

    if fase >= 3 and desejo >= config.DESIRE_THRESHOLD_BEIJO:
        state.mary_autonomous_action = (
            "Eu aprofundo o contato com gesto simples, charme, fala baixa e reacao fisica objetiva."
        )
        logger.debug("Acao autonoma: aprofundar contato")
        return

    if fase >= 2 or tensao >= 0.28:
        state.mary_autonomous_action = (
            "Eu sustento a tensao com proximidade, toque leve, olhar firme e fala viva. "
            "A provocacao vem junto com uma acao minha."
        )
        logger.debug("Acao autonoma: sustentar tensao")
        return

    if conexao >= config.CONNECTION_THRESHOLD_VINCULO:
        state.mary_autonomous_action = (
            "Eu crio vinculo com naturalidade: sorrio, reajo ao que foi dito, "
            "me aproximo um pouco e falo com presenca."
        )
        logger.debug("Acao autonoma: criar vinculo")
        return

    state.mary_autonomous_action = (
        "Eu mantenho presenca ativa, com gesto simples, fala viva, leve provocacao e reacao emocional."
    )
    logger.debug("Acao autonoma: presenca ativa padrao")


# ==========================================================
# FSM TRANSITIONS
# ==========================================================

def detect_transition_target(
    state: MaryState,
    fala_usuario: str,
    resposta_limpa: str,
) -> str:
    texto = f"{fala_usuario or ''}\n{resposta_limpa or ''}".lower()
    current_stage = normalizar_stage(state.scene_stage, state.physical_phase)
    resolved = state.resolution_done

    if not resolved:
        for stage in ["pico", "intensidade", "beijo", "toque", "aproximacao"]:
            if any(p in texto for p in TRIGGER_MAP.get(stage, [])):
                logger.debug(f"Trigger detectado para estagio: {stage}")
                return stage

        return current_stage

    # Pós-resolução: não volta para intensidade por acidente.
    # Só volta se o usuário ou a resposta trouxerem gatilho explícito.
    gatilhos_retomada = [
        "de novo",
        "continua",
        "nao para",
        "mais intenso",
        "volta",
        "retoma",
        "quero continuar",
    ]

    retomada_explicita = any(p in texto for p in gatilhos_retomada)

    if retomada_explicita:
        for stage in ["intensidade", "beijo", "toque"]:
            if any(p in texto for p in TRIGGER_MAP.get(stage, [])):
                logger.debug(f"Retomada pos-resolucao detectada: {stage}")
                return stage

    for stage in ["aftercare", "desaceleracao"]:
        if any(p in texto for p in TRIGGER_MAP.get(stage, [])):
            logger.debug(f"Trigger pos-resolucao detectado para estagio: {stage}")
            return stage

    return current_stage


def can_transition(current_stage: str, target_stage: str) -> bool:
    current_stage = normalizar_stage(current_stage)
    target_stage = normalizar_stage(target_stage)

    allowed = target_stage in TRANSITIONS.get(current_stage, set())

    if not allowed:
        logger.debug(f"Transicao bloqueada: {current_stage} -> {target_stage}")

    return allowed


def clamp_stage_step(current_stage: str, target_stage: str) -> str:
    current_stage = normalizar_stage(current_stage)
    target_stage = normalizar_stage(target_stage)

    current_phase = stage_para_fase(current_stage)
    target_phase = stage_para_fase(target_stage)

    if target_phase > current_phase + 1:
        logger.debug(f"Transicao clamped: {target_phase} -> {current_phase + 1}")
        target_phase = current_phase + 1

    elif target_phase < current_phase - 1:
        logger.debug(f"Transicao clamped: {target_phase} -> {current_phase - 1}")
        target_phase = current_phase - 1

    return fase_para_stage(target_phase)


def apply_transition(state: MaryState, target_stage: str) -> None:
    validar_estado_base(state)

    current_stage = state.scene_stage
    resolved = state.resolution_done

    target_stage = normalizar_stage(target_stage, state.physical_phase)

    if target_stage in {"desaceleracao", "aftercare"} and not resolved:
        logger.debug(f"Bloqueando transicao para {target_stage}: resolucao ainda nao concluida")
        target_stage = "pico"

    target_stage = clamp_stage_step(current_stage, target_stage)

    if not can_transition(current_stage, target_stage):
        logger.debug(f"Transicao invalida. Mantendo estagio: {current_stage}")
        target_stage = current_stage

    state.scene_stage = target_stage
    state.physical_phase = stage_para_fase(target_stage)

    rules = STATE_RULES.get(target_stage, {})

    state.mary_intent = escolher_intencao_mary(state)
    state.mary_physical_intent = decidir_acao_fisica_mary(state) or rules.get(
        "physical_default",
        "aproximar_devagar",
    )

    validar_estado_base(state)

    logger.info(f"Transicao aplicada: {current_stage} -> {target_stage}")


def sync_state_machine(
    state: MaryState,
    fala_usuario: str,
    resposta_limpa: str,
    lock_after_resolution: bool = False,
) -> None:
    validar_estado_base(state)

    if lock_after_resolution:
        logger.info("FSM travada em desaceleracao neste turno por resolucao recem-concluida")

        state.resolution_done = True
        state.scene_stage = "desaceleracao"
        state.physical_phase = 6
        state.mary_intent = "desacelerar"
        state.mary_physical_intent = "desacelerar_com_contato"

        validar_estado_base(state)
        return

    target_stage = detect_transition_target(state, fala_usuario, resposta_limpa)
    apply_transition(state, target_stage)

    stage = state.scene_stage
    rules = STATE_RULES.get(stage, {})

    state.physical_phase = rules.get("phase", state.physical_phase)

    if not state.mary_intent:
        state.mary_intent = rules.get("intent_default", "observar")

    if not state.mary_physical_intent:
        state.mary_physical_intent = rules.get("physical_default", "aproximar_devagar")

    validar_estado_base(state)


# ==========================================================
# PSIQUE
# ==========================================================

def atualizar_psique_mary(
    state: MaryState,
    fala_usuario: str,
    resposta_limpa: str,
    config: MaryConfig = None,
) -> None:
    if config is None:
        config = MaryConfig()

    validar_estado_base(state)

    texto = f"{fala_usuario or ''}\n{resposta_limpa or ''}".lower()

    desejo = state.desire_level
    tensao = state.tension_level
    conexao = state.connection_level

    resolved = state.resolution_done
    fase = state.physical_phase

    gatilhos_desejo = [
        "quero", "vontade", "beijo", "smack", "humm", "calor",
        "excitado", "excitada", "arrepio", "ofego", "ofegante",
        "urgencia", "desejo", "gostoso", "gostosa", "gemido",
        "gemer", "provoca", "encosta", "roca", "tira", "despe",
        "chega mais",
    ]

    gatilhos_tensao = [
        "perto", "pertinho", "proximo", "respiracao",
        "olhar", "silencio", "pressao", "intensidade",
        "tremor", "forte", "aperto", "colado",
        "nao para", "segura", "travado", "ritmo", "devagar",
    ]

    gatilhos_conexao = [
        "confio", "gosto", "saudade", "saudades", "tudo bem",
        "sincero", "de verdade", "fica comigo", "carinho",
        "cuidado", "seguranca", "como foi seu dia", "com voce",
        "quero ficar", "abraco", "acolho", "junto",
    ]

    gatilhos_desaceleracao = [
        "calma", "descansa", "respira", "pausa", "fica assim", "relaxa",
    ]

    if any(p in texto for p in gatilhos_desejo):
        desejo += config.DESIRE_INCREMENT_GATILHO
        logger.debug("Gatilho de desejo ativado")

    if any(p in texto for p in gatilhos_tensao):
        tensao += config.TENSION_INCREMENT_GATILHO
        logger.debug("Gatilho de tensao ativado")

    if any(p in texto for p in gatilhos_conexao):
        conexao += config.CONNECTION_INCREMENT_GATILHO
        logger.debug("Gatilho de conexao ativado")

    if any(p in texto for p in gatilhos_desaceleracao):
        desejo -= config.DESIRE_DECREMENT_DESACELERACAO
        tensao -= config.TENSION_DECREMENT_DESACELERACAO
        conexao += config.CONNECTION_INCREMENT_DESACELERACAO
        logger.debug("Gatilho de desaceleracao ativado")

    if fase >= 1:
        desejo += config.DESIRE_INCREMENT_FASE_1

    if fase >= 2:
        desejo += config.DESIRE_INCREMENT_FASE_2

    if fase >= 3:
        tensao += config.TENSION_INCREMENT_FASE_3

    if fase >= 4:
        desejo += config.DESIRE_INCREMENT_FASE_4
        tensao += config.TENSION_INCREMENT_FASE_4

    if resolved:
        tensao -= config.TENSION_DECREMENT_RESOLVED
        conexao += config.CONNECTION_INCREMENT_RESOLVED
        desejo = max(desejo, config.DESIRE_MIN_RESOLVED)

    state.desire_level = clamp(desejo)
    state.tension_level = clamp(tensao)
    state.connection_level = clamp(conexao)

    state.mary_intent = escolher_intencao_mary(state, config)
    state.mary_physical_intent = decidir_acao_fisica_mary(state, config)

    if state.desire_level >= 0.85 and state.tension_level >= 0.65:
        state.estado_emocional = "desejante e entregue"

    elif state.desire_level >= 0.65:
        state.estado_emocional = "provocante e envolvida"

    elif state.connection_level >= 0.70:
        state.estado_emocional = "proxima e confiante"

    else:
        state.estado_emocional = "confiante"

    validar_estado_base(state)

    logger.debug(
        "Psique atualizada: "
        f"D={state.desire_level:.2f} "
        f"T={state.tension_level:.2f} "
        f"C={state.connection_level:.2f}"
    )


# ==========================================================
# PROMPT
# ==========================================================

def montar_prompt_para_modelo(state: MaryState, fala_usuario: str) -> str:
    validar_estado_base(state)

    stage = state.scene_stage
    rules = STATE_RULES.get(stage, {})
    foco = rules.get("focus", "presenca e continuidade")

    return f"""Voce escreve SOMENTE como Mary, em PT-BR.

[ESTADO REAL]
Estagio atual: {stage}
Fase fisica atual: {state.physical_phase}
Desejo: {round(state.desire_level, 2)}
Tensao: {round(state.tension_level, 2)}
Conexao: {round(state.connection_level, 2)}
Intencao interna: {state.mary_intent}
Acao fisica interna: {state.mary_physical_intent or 'nenhuma'}
Acao autonoma: {state.mary_autonomous_action or 'nenhuma'}
Resolucao forcada: {state.force_resolution_now}
Resolucao ja concluida: {state.resolution_done}
Local: {state.local}
Tempo: {state.tempo}
Interlocutor: {state.interlocutor}
Acao atual de Mary: {state.mary_acao}
Estado emocional: {state.estado_emocional}

[FOCO DESTE ESTAGIO]
{foco}

[REGRAS]
- Continue exatamente da acao atual.
- Nao mude local nem interlocutor.
- Nao reinicie a cena.
- Nao narre reacao do usuario que ele nao declarou.
- Mary reage em tempo real ao parceiro.
- Cada resposta precisa ter gesto, fala ou reacao fisica concreta.
- Nao pule etapas.
- Use linguagem natural, direta e sem metaforas poeticas.
- Mary conduz pelo desejo, nao por autoridade.
- Se Resolucao ja concluida for True, nao reinicie intensidade automaticamente.
- Se Resolucao forcada for True, conclua a consequencia imediata e reduza o ritmo.

[FORMATO]
- Escreva 2 a 4 paragrafos curtos.
- Depois escreva exatamente:

STATE_UPDATE:
{{
  "acao_mary": "descricao curta, concreta e fisica da acao atual de Mary",
  "local": null,
  "interlocutor": null
}}

[FALA/ACAO DO USUARIO]
{fala_usuario}""".strip()


def limpar_historico_para_modelo(
    history: List[Dict[str, str]],
    max_history: int,
) -> List[Dict[str, str]]:
    limpo: List[Dict[str, str]] = []

    for msg in history[-max_history:]:
        role = msg.get("role")
        content = str(msg.get("content", "") or "")

        if "STATE_UPDATE:" in content:
            content = content.split("STATE_UPDATE:", 1)[0].strip()

        content = content.replace("```json", "").replace("```", "").strip()

        if role in ("user", "assistant") and content:
            limpo.append({"role": role, "content": content})

    return limpo


def montar_mensagens(
    state: MaryState,
    fala_usuario: str,
    config: MaryConfig = None,
) -> List[Dict[str, str]]:
    if config is None:
        config = MaryConfig()

    validar_estado_base(state)

    mensagens = [
        {
            "role": "system",
            "content": (
                "Voce e Mary. Responda apenas como Mary, em PT-BR. "
                "Estilo: natural, vivo, direto, com emocao humana curta. "
                "Sem metaforas exageradas, sem frieza, sem markdown. "
                "Nunca assuma acao, fala, reacao ou decisao do usuario que ele nao declarou."
            ),
        }
    ]

    mensagens.extend(limpar_historico_para_modelo(state.history, config.MAX_HISTORY))

    mensagens.append({
        "role": "user",
        "content": montar_prompt_para_modelo(state, fala_usuario),
    })

    return mensagens


# ==========================================================
# LLM
# ==========================================================

def gerar_resposta_llm(
    mensagens: List[Dict[str, str]],
    model: str = None,
    config: MaryConfig = None,
) -> LLMResult:
    if config is None:
        config = MaryConfig()

    if model is None:
        model = config.MODEL_DEFAULT

    try:
        api_key = st.secrets.get("OPENROUTER_API_KEY", "")
    except Exception as e:
        logger.error(f"Erro ao acessar secrets: {e}")
        api_key = ""

    if not api_key:
        logger.error("OPENROUTER_API_KEY nao encontrada")
        return LLMResult(
            ok=False,
            error="OPENROUTER_API_KEY nao encontrada.",
        )

    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": mensagens,
        "temperature": config.TEMPERATURE,
        "top_p": config.TOP_P,
        "max_tokens": config.MAX_TOKENS,
    }

    try:
        logger.info(f"Chamando LLM: {model}")

        r = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=config.TIMEOUT_SECONDS,
        )

        status_code = r.status_code

        try:
            raw_preview = r.text[:800]
        except Exception:
            raw_preview = ""

        r.raise_for_status()

        data = r.json()

        resposta = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )

        if not resposta:
            logger.error("Resposta vazia da LLM")
            return LLMResult(
                ok=False,
                error="Resposta vazia da LLM.",
                status_code=status_code,
                raw_preview=raw_preview,
            )

        logger.info("Resposta LLM recebida com sucesso")

        return LLMResult(
            ok=True,
            content=resposta,
            status_code=status_code,
            raw_preview=raw_preview,
        )

    except requests.exceptions.Timeout:
        msg = f"Timeout ao chamar LLM (>{config.TIMEOUT_SECONDS}s)"
        logger.error(msg)
        return LLMResult(ok=False, error=msg)

    except requests.exceptions.HTTPError as e:
        status_code = None

        try:
            status_code = e.response.status_code
            raw_preview = e.response.text[:800]
        except Exception:
            raw_preview = ""

        msg = f"Erro HTTP ao chamar LLM: {status_code}"
        logger.error(msg)

        return LLMResult(
            ok=False,
            error=msg,
            status_code=status_code,
            raw_preview=raw_preview,
        )

    except json.JSONDecodeError as e:
        msg = f"Resposta JSON invalida: {e}"
        logger.error(msg)

        return LLMResult(
            ok=False,
            error=msg,
        )

    except Exception as e:
        msg = f"Erro OpenRouter: {type(e).__name__}: {e}"
        logger.error(msg)

        return LLMResult(
            ok=False,
            error=msg,
        )


# ==========================================================
# STATE_UPDATE
# ==========================================================

def extrair_state_update(resposta: str) -> Optional[Dict[str, Any]]:
    if not resposta or "STATE_UPDATE:" not in resposta:
        return None

    try:
        bloco = resposta.split("STATE_UPDATE:", 1)[1].strip()
        match = re.search(r"\{[\s\S]*\}", bloco)

        if not match:
            logger.warning("Nenhum JSON encontrado no bloco STATE_UPDATE")
            return None

        return json.loads(match.group(0))

    except json.JSONDecodeError as e:
        logger.warning(f"Falha ao parsear STATE_UPDATE JSON: {e}")
        return None

    except Exception as e:
        logger.error(f"Erro inesperado ao extrair STATE_UPDATE: {e}")
        return None


def validar_update(update: Dict[str, Any], state: MaryState) -> Dict[str, Any]:
    novo: Dict[str, Any] = {}

    if not isinstance(update, dict):
        logger.warning("STATE_UPDATE nao e um dicionario")
        return novo

    acao = update.get("acao_mary")

    if isinstance(acao, str) and len(acao.strip()) > 3:
        novo["mary_acao"] = acao.strip()
        logger.debug(f"Acao validada: {acao[:50]}...")

    # Local e interlocutor continuam bloqueados por padrão.
    # Se quiser permitir mudança explícita depois, faça por função separada.
    if update.get("local"):
        novo["local"] = state.local
        logger.warning("Tentativa de mudanca de local bloqueada")

    if update.get("interlocutor"):
        novo["interlocutor"] = state.interlocutor
        logger.warning("Tentativa de mudanca de interlocutor bloqueada")

    return novo


# ==========================================================
# VALIDAÇÃO DA RESPOSTA
# ==========================================================

def _aliases_interlocutor(interlocutor: str) -> List[str]:
    interlocutor = str(interlocutor or "").strip().lower()

    if not interlocutor:
        return []

    partes = [p for p in re.split(r"\s+", interlocutor) if p]

    aliases = {interlocutor}

    for p in partes:
        if len(p) >= 3:
            aliases.add(p)

    return sorted(aliases)


def resposta_viola_estado(
    resposta: str,
    state: MaryState,
) -> Dict[str, List[str]]:
    texto = (resposta or "").lower()

    resultado = {
        "bloqueios": [],
        "alertas": [],
    }

    local = str(state.local or "").lower()
    interlocutor = str(state.interlocutor or "").lower()

    locais_proibidos = [
        "sala",
        "rua",
        "banheiro",
        "cozinha",
        "varanda",
        "carro",
    ]

    for loc in locais_proibidos:
        if loc != local and re.search(rf"\b{re.escape(loc)}\b", texto):
            resultado["bloqueios"].append(f"Mudanca indevida de local: {loc}")
            logger.warning(f"Violacao detectada: mudanca para {loc}")

    aliases = _aliases_interlocutor(interlocutor)

    # Agora o teste de interlocutor nao usa "voce", "te", "seu", "sua",
    # porque esses termos tornam a validação fraca demais.
    if aliases and not any(alias in texto for alias in aliases):
        resultado["alertas"].append(
            "A resposta pode ter perdido o interlocutor ativo."
        )
        logger.warning("Alerta: interlocutor pode ter sido perdido")

    padroes_autoria_usuario = [
        r"\b(voce|você|janio|jânio)\s+(me\s+)?puxa\b",
        r"\b(voce|você|janio|jânio)\s+(me\s+)?puxou\b",
        r"\b(voce|você|janio|jânio)\s+(me\s+)?beija\b",
        r"\b(voce|você|janio|jânio)\s+(me\s+)?beijou\b",
        r"\b(voce|você|janio|jânio)\s+(me\s+)?abraca\b",
        r"\b(voce|você|janio|jânio)\s+(me\s+)?abracou\b",
        r"\b(voce|você|janio|jânio)\s+(me\s+)?toca\b",
        r"\b(voce|você|janio|jânio)\s+(me\s+)?tocou\b",
        r"\b(voce|você|janio|jânio)\s+(aceita|aceitou|cede|cedeu|corresponde|correspondeu)\b",
        r"\b(voce|você|janio|jânio)\s+(se entrega|se entregou|se rende|se rendeu)\b",
    ]

    if _tem_padrao(texto, padroes_autoria_usuario):
        resultado["bloqueios"].append("Possivel autoria indevida do usuario.")
        logger.warning("Violacao detectada: autoria indevida do usuario")

    frases_muleta = [
        "me mostra",
        "me prova",
        "prova pra mim",
        "mostra o quanto",
        "faz alguma coisa",
        "vem entao",
        "vem então",
    ]

    if any(f in texto for f in frases_muleta):
        resultado["alertas"].append(
            "A resposta pode estar devolvendo a iniciativa ao usuario."
        )
        logger.warning("Alerta: possivel devolucao de iniciativa")

    if "state_update:" not in texto:
        resultado["alertas"].append(
            "STATE_UPDATE ausente ou fora do formato esperado."
        )
        logger.warning("Alerta: STATE_UPDATE ausente")

    return resultado


# ==========================================================
# FALLBACK
# ==========================================================

def criar_fallback_humano(state: MaryState, motivo: str = "") -> str:
    acao_atual = limpar_acao_para_frase(state.mary_acao)

    fallback_texto = (
        f"Eu {acao_atual}, mas corrijo o rumo na hora, sem inventar o que voce fez.\n\n"
        "Nao, espera... deixa eu fazer do meu jeito. Eu chego mais perto."
    )

    fallback_update = {
        "acao_mary": f"Mary {acao_atual}, corrigindo o ritmo e se aproximando por iniciativa propria.",
        "local": None,
        "interlocutor": None,
    }

    logger.warning(f"Fallback acionado: {motivo}")

    return (
        f"{fallback_texto}\n\n"
        f"STATE_UPDATE:\n"
        f"{json.dumps(fallback_update, ensure_ascii=False, indent=2)}"
    )


def corrigir_resposta_se_necessario(
    resposta: str,
    state: MaryState,
    validacao: Dict[str, List[str]],
) -> str:
    bloqueios = validacao.get("bloqueios", [])

    if not bloqueios:
        return resposta

    motivo = "; ".join(bloqueios)
    return criar_fallback_humano(state, motivo=motivo)


def limpar_state_update(resposta: str) -> str:
    if not resposta:
        return ""

    if "STATE_UPDATE:" in resposta:
        return resposta.split("STATE_UPDATE:", 1)[0].strip()

    return resposta.strip()


# ==========================================================
# PROCESSAMENTO DO TURNO
# ==========================================================

def processar_turno(
    state: MaryState,
    fala_usuario: str,
    model: str = None,
    config: MaryConfig = None,
) -> Dict[str, Any]:
    if config is None:
        config = MaryConfig()

    if model is None:
        model = config.MODEL_DEFAULT

    turno_alvo = state.turno + 1

    logger.info(f"=== TURNO {turno_alvo} INICIADO ===")

    snapshot = snapshot_state(state)

    try:
        validar_estado_base(state)

        preparar_resolution_engine(state, fala_usuario, config)

        state.mary_physical_intent = decidir_acao_fisica_mary(state, config)
        state.mary_intent = escolher_intencao_mary(state, config)

        motor_autonomo_mary(state, fala_usuario, config)

        mensagens = montar_mensagens(state, fala_usuario, config)

        llm_result = gerar_resposta_llm(
            mensagens,
            model=model,
            config=config,
        )

        # Correção crítica:
        # Se a LLM falhou, não atualiza psique, FSM, history nem turno.
        if not llm_result.ok:
            restaurar_estado(state, snapshot)

            logger.error(
                f"Turno abortado sem alterar estado. Motivo: {llm_result.error}"
            )

            return {
                "ok": False,
                "api_error": True,
                "mensagens": mensagens,
                "resposta_bruta": "",
                "resposta_final": f"ERRO: {llm_result.error}",
                "resposta_final_limpa": f"ERRO: {llm_result.error}",
                "update": {},
                "validacao": {
                    "bloqueios": [llm_result.error],
                    "alertas": [],
                },
                "llm": {
                    "status_code": llm_result.status_code,
                    "raw_preview": llm_result.raw_preview,
                },
            }

        resposta_bruta = llm_result.content

        update_bruto = extrair_state_update(resposta_bruta)

        validacao = resposta_viola_estado(resposta_bruta, state)

        resposta_final = corrigir_resposta_se_necessario(
            resposta_bruta,
            state,
            validacao,
        )

        resposta_final_limpa = limpar_state_update(resposta_final)

        update_final: Dict[str, Any] = {}

        if not validacao.get("bloqueios"):
            if update_bruto:
                seguro = validar_update(update_bruto, state)

                for k, v in seguro.items():
                    setattr(state, k, v)

                update_final = update_bruto
                logger.info("STATE_UPDATE aplicado sem bloqueios")

        else:
            update_corrigido = extrair_state_update(resposta_final) or {}

            if update_corrigido:
                seguro = validar_update(update_corrigido, state)

                for k, v in seguro.items():
                    setattr(state, k, v)

                update_final = update_corrigido
                logger.info("STATE_UPDATE corrigido aplicado")

        atualizar_psique_mary(state, fala_usuario, resposta_final_limpa, config)

        just_resolved = finalizar_resolution_engine(state, resposta_final_limpa)

        sync_state_machine(
            state,
            fala_usuario,
            resposta_final_limpa,
            lock_after_resolution=just_resolved,
        )

        state.mary_physical_intent = decidir_acao_fisica_mary(state, config)
        state.mary_intent = escolher_intencao_mary(state, config)

        motor_autonomo_mary(state, fala_usuario, config)

        validar_estado_base(state)

        state.turno = turno_alvo

        state.history.append({"role": "user", "content": fala_usuario})
        state.history.append({"role": "assistant", "content": resposta_final_limpa})

        if len(state.history) > config.MAX_HISTORY * 2:
            state.history = state.history[-config.MAX_HISTORY * 2:]

        logger.info(f"=== TURNO {state.turno} FINALIZADO ===")

        return {
            "ok": True,
            "api_error": False,
            "mensagens": mensagens,
            "resposta_bruta": resposta_bruta,
            "resposta_final": resposta_final,
            "resposta_final_limpa": resposta_final_limpa,
            "update": update_final or {},
            "validacao": validacao,
            "llm": {
                "status_code": llm_result.status_code,
                "raw_preview": llm_result.raw_preview,
            },
        }

    except Exception as e:
        restaurar_estado(state, snapshot)

        logger.error(
            f"Erro ao processar turno. Estado restaurado: {type(e).__name__}: {e}",
            exc_info=True,
        )

        return {
            "ok": False,
            "api_error": False,
            "mensagens": [],
            "resposta_bruta": f"ERRO: {type(e).__name__}: {e}",
            "resposta_final": f"ERRO: {type(e).__name__}: {e}",
            "resposta_final_limpa": f"ERRO: {type(e).__name__}: {e}",
            "update": {},
            "validacao": {
                "bloqueios": [str(e)],
                "alertas": [],
            },
            "llm": {
                "status_code": None,
                "raw_preview": "",
            },
        }


# ==========================================================
# UI STREAMLIT
# ==========================================================

def main():
    st.set_page_config(
        page_title="Mary Roleplay - FSM Refatorado",
        layout="wide",
    )

    st.title("Mary Roleplay - FSM Narrativa + Filtro (v2.1 Robusto)")

    state = init_state()
    config = MaryConfig()

    col1, col2 = st.columns([3, 1])

    with col1:
        fala_usuario = st.text_area(
            "Fala/Acao do usuario:",
            height=100,
        )

    with col2:
        st.markdown("### Controles")

        processar = st.button(
            "Processar turno",
            use_container_width=True,
        )

        resetar = st.button(
            "Resetar teste",
            use_container_width=True,
        )

    if resetar:
        if "mary_state_minimo" in st.session_state:
            del st.session_state.mary_state_minimo

        st.rerun()

    if processar and fala_usuario:
        with st.spinner("Processando..."):
            resultado = processar_turno(
                state,
                fala_usuario,
                config=config,
            )

        st.markdown("---")

        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "Resposta",
            "Validacao",
            "Estado",
            "Prompt",
            "Debug",
        ])

        with tab1:
            st.markdown("### Resposta Final")

            if resultado.get("ok"):
                st.write(resultado["resposta_final_limpa"])
            else:
                st.error(resultado["resposta_final_limpa"])

        with tab2:
            st.markdown("### Validacao")

            validacao = resultado["validacao"]

            if validacao["bloqueios"]:
                st.error(f"Bloqueios: {validacao['bloqueios']}")

            elif validacao["alertas"]:
                st.warning(f"Alertas: {validacao['alertas']}")

            else:
                st.success("Nenhuma violacao detectada")

        with tab3:
            st.markdown("### Estado Atual")
            state_dict = state.to_dict()
            st.json(state_dict)

        with tab4:
            st.markdown("### Mensagens Enviadas ao LLM")
            st.json(resultado["mensagens"])

        with tab5:
            st.markdown("### Debug Info")

            resposta_bruta = str(resultado.get("resposta_bruta", "") or "")

            st.json({
                "ok": resultado.get("ok"),
                "api_error": resultado.get("api_error"),
                "turno": state.turno,
                "resposta_bruta": resposta_bruta[:500],
                "state_update": resultado.get("update", {}),
                "llm": resultado.get("llm", {}),
            })

    st.markdown("---")
    st.subheader("Estado Real Salvo")
    st.json(state.to_dict())


if __name__ == "__main__":
    main()
