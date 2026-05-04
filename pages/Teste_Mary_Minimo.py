import re
import json
import logging
import streamlit as st
import requests
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


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
    APROXIMAR = "aproximar"
    PROVOCAR = "provocar"
    TOCAR = "tocar"
    BEIJAR = "beijar"
    INTENSIFICAR = "intensificar"
    RESOLVER_PICO = "resolver_pico"
    DESACELERAR = "desacelerar"
    AFTERCARE = "aftercare"
    REACENDER = "reacender"


class PhysicalIntent(str, Enum):
    PRESENCA = "presenca"
    APROXIMAR = "aproximar"
    TOCAR = "tocar"
    BEIJAR = "beijar"
    INTENSIFICAR = "intensificar"
    RESOLVER = "resolver"
    DESACELERAR = "desacelerar"
    CUIDAR = "cuidar"
    REACENDER = "reacender"


# ==========================================================
# CONFIG
# ==========================================================
@dataclass
class MaryConfig:
    MODEL_DEFAULT: str = "google/gemini-3-flash-preview"
    MAX_HISTORY: int = 6
    TEMPERATURE: float = 0.70
    TOP_P: float = 0.92
    MAX_TOKENS: int = 520
    TIMEOUT_SECONDS: int = 60

    # Modo livre: impede loop de preliminar e força progressão quando há receptividade.
    MARY_LIVRE: bool = True

    # Limiares
    DESIRE_THRESHOLD_APROXIMACAO: float = 0.25
    DESIRE_THRESHOLD_TOQUE: float = 0.40
    DESIRE_THRESHOLD_BEIJO: float = 0.55
    DESIRE_THRESHOLD_INTENSIDADE: float = 0.68
    DESIRE_THRESHOLD_PICO: float = 0.88

    TENSION_THRESHOLD_APROXIMACAO: float = 0.28
    TENSION_THRESHOLD_INTENSIDADE: float = 0.45
    TENSION_THRESHOLD_PICO: float = 0.72

    CONNECTION_THRESHOLD_REACENDER: float = 0.70
    CONNECTION_THRESHOLD_AFTERCARE: float = 0.70

    # Incrementos mais suaves para evitar tudo bater em 1.0 cedo demais
    DESIRE_INCREMENT_GATILHO: float = 0.10
    TENSION_INCREMENT_GATILHO: float = 0.08
    CONNECTION_INCREMENT_GATILHO: float = 0.08

    DESIRE_DECREMENT_RESOLVED: float = 0.18
    TENSION_DECREMENT_RESOLVED: float = 0.22
    CONNECTION_INCREMENT_RESOLVED: float = 0.08

    DESIRE_MIN_REACENDIMENTO: float = 0.72
    TENSION_MIN_REACENDIMENTO: float = 0.50
    CONNECTION_MIN_REACENDIMENTO: float = 0.82


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

    mary_acao: str = "Mary está sentada na beira da cama, atenta à presença de Janio"
    estado_emocional: str = "confiante"
    style_profile: str = "natural_viva_direta"

    turno: int = 0
    history: List[Dict[str, str]] = field(default_factory=list)

    physical_phase: int = 0
    scene_stage: str = SceneStage.INICIO.value

    desire_level: float = 0.18
    tension_level: float = 0.12
    connection_level: float = 0.22

    mary_intent: str = MaryIntent.OBSERVAR.value
    mary_physical_intent: str = PhysicalIntent.PRESENCA.value

    resolution_done: bool = False
    shared_resolution_done: bool = False
    force_resolution_now: bool = False

    cycle_count: int = 1
    reignited_aftercare: bool = False
    consequence_locked: bool = False

    mary_autonomous_action: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "personagem": self.personagem,
            "timeline": self.timeline,
            "local": self.local,
            "tempo": self.tempo,
            "interlocutor": self.interlocutor,
            "mary_acao": self.mary_acao,
            "estado_emocional": self.estado_emocional,
            "modo": self.modo,
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
            "shared_resolution_done": self.shared_resolution_done,
            "force_resolution_now": self.force_resolution_now,
            "cycle_count": self.cycle_count,
            "reignited_aftercare": self.reignited_aftercare,
            "consequence_locked": self.consequence_locked,
            "mary_autonomous_action": self.mary_autonomous_action,
            "style_profile": self.style_profile,
        }


# ==========================================================
# RULES
# ==========================================================
STATE_RULES: Dict[str, Dict[str, Any]] = {
    "inicio": {
        "phase": 0,
        "intent_default": MaryIntent.OBSERVAR.value,
        "physical_default": PhysicalIntent.PRESENCA.value,
        "focus": "presença, fala viva, convite curto, sem relatório corporal",
    },
    "aproximacao": {
        "phase": 1,
        "intent_default": MaryIntent.APROXIMAR.value,
        "physical_default": PhysicalIntent.APROXIMAR.value,
        "focus": "aproximar com naturalidade, fala antes da descrição",
    },
    "toque": {
        "phase": 2,
        "intent_default": MaryIntent.TOCAR.value,
        "physical_default": PhysicalIntent.TOCAR.value,
        "focus": "toque como ponte, não como destino; evitar nuca/pescoço em loop",
    },
    "beijo": {
        "phase": 3,
        "intent_default": MaryIntent.INTENSIFICAR.value,
        "physical_default": PhysicalIntent.INTENSIFICAR.value,
        "focus": "beijo como ponte curta para intensidade; não permanecer em beijo, nuca, pescoço ou respiração",
    },
    "intensidade": {
        "phase": 4,
        "intent_default": MaryIntent.INTENSIFICAR.value,
        "physical_default": PhysicalIntent.INTENSIFICAR.value,
        "focus": "ação decisiva, fala viva, progressão concreta; sem enrolar em preliminar repetitiva",
    },
    "pico": {
        "phase": 5,
        "intent_default": MaryIntent.RESOLVER_PICO.value,
        "physical_default": PhysicalIntent.RESOLVER.value,
        "focus": "resolução do pico com consequência clara; não cortar para descanso cedo demais",
    },
    "desaceleracao": {
        "phase": 6,
        "intent_default": MaryIntent.DESACELERAR.value,
        "physical_default": PhysicalIntent.DESACELERAR.value,
        "focus": "reduzir ritmo com presença, fala íntima e consequência do que aconteceu",
    },
    "aftercare": {
        "phase": 7,
        "intent_default": MaryIntent.AFTERCARE.value,
        "physical_default": PhysicalIntent.CUIDAR.value,
        "focus": "cuidado, presença e vínculo; pode reacender se o usuário provocar",
    },
}

TRANSITIONS: Dict[str, set] = {
    "inicio": {"inicio", "aproximacao", "toque"},
    "aproximacao": {"aproximacao", "toque", "beijo", "intensidade"},
    "toque": {"toque", "beijo", "intensidade"},
    "beijo": {"beijo", "intensidade", "pico"},
    "intensidade": {"intensidade", "pico"},
    "pico": {"pico", "desaceleracao"},
    "desaceleracao": {"desaceleracao", "aftercare", "intensidade"},
    "aftercare": {"aftercare", "toque", "beijo", "intensidade"},
}


PHYSICAL_HINTS = {
    "presenca": "Mary usa fala viva, olhar e gesto simples; pouca narração.",
    "aproximar": "Mary se aproxima sem relatório corporal; fala primeiro, gesto curto depois.",
    "tocar": "Mary usa um toque objetivo e uma fala viva; não empilha ações.",
    "beijar": "Mary sustenta o beijo por pouco tempo e logo muda a dinâmica.",
    "intensificar": "Mary avança a cena com decisão; não repete beijo, nuca ou pescoço.",
    "resolver": "Mary conduz o pico com consequência clara e sem cortar para aftercare cedo.",
    "desacelerar": "Mary reduz o ritmo, mas reconhece o que aconteceu.",
    "cuidar": "Mary fica próxima e fala com intimidade; não vira descrição longa.",
    "reacender": "Mary retoma com memória do ciclo anterior, sem reiniciar do zero.",
}


# ==========================================================
# HELPERS
# ==========================================================
def clamp(v: float, min_v: float = 0.0, max_v: float = 1.0) -> float:
    try:
        v = float(v)
    except (ValueError, TypeError):
        v = min_v
    return max(min_v, min(max_v, v))


def fase_para_stage(phase: int) -> str:
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
    return {
        "inicio": 0,
        "aproximacao": 1,
        "toque": 2,
        "beijo": 3,
        "intensidade": 4,
        "pico": 5,
        "desaceleracao": 6,
        "aftercare": 7,
    }.get((stage or "").strip().lower(), 0)


def init_state() -> MaryState:
    if "mary_state_minimo" not in st.session_state:
        st.session_state.mary_state_minimo = MaryState()
        logger.info("Estado inicial de Mary criado")
    return st.session_state.mary_state_minimo


def limpar_state_update(resposta: str) -> str:
    if not resposta:
        return ""
    if "STATE_UPDATE:" in resposta:
        return resposta.split("STATE_UPDATE:", 1)[0].strip()
    return resposta.strip()


def extrair_state_update(resposta: str) -> Optional[Dict[str, Any]]:
    if not resposta or "STATE_UPDATE:" not in resposta:
        return None

    try:
        bloco = resposta.split("STATE_UPDATE:", 1)[1].strip()
        match = re.search(r"\{[\s\S]*\}", bloco)
        if not match:
            return None
        return json.loads(match.group(0))
    except Exception as e:
        logger.warning(f"Falha ao extrair STATE_UPDATE: {type(e).__name__}: {e}")
        return None


def validar_update(update: Dict[str, Any], state: MaryState) -> Dict[str, Any]:
    novo: Dict[str, Any] = {}
    if not isinstance(update, dict):
        return novo

    acao = update.get("acao_mary")
    if isinstance(acao, str) and len(acao.strip()) > 3:
        novo["mary_acao"] = acao.strip()

    # Bloqueia mudanças indevidas via LLM.
    if update.get("local"):
        novo["local"] = state.local
    if update.get("interlocutor"):
        novo["interlocutor"] = state.interlocutor

    return novo


def detectar_receptividade(fala_usuario: str) -> bool:
    texto = (fala_usuario or "").lower()
    sinais = [
        "continua", "assim", "mais", "não para", "nao para",
        "quero", "vem", "vai", "humm", "ahh", "ahhh",
        "perfeito", "adorei", "delícia", "delicia",
        "gostoso", "gostosa", "tesão", "tesao",
        "smack", "chup", "...", "sim",
    ]
    return any(s in texto for s in sinais)


def detectar_pico_usuario(fala_usuario: str) -> bool:
    texto = (fala_usuario or "").lower()
    sinais = [
        "vou gozar", "vou chegar", "estou gozando", "tô gozando",
        "to gozando", "vou explodir", "vem junto", "agora",
    ]
    return any(s in texto for s in sinais)


def detectar_reacendimento_pos_aftercare(state: MaryState, fala_usuario: str) -> bool:
    texto = (fala_usuario or "").lower()

    if state.scene_stage not in {"aftercare", "desaceleracao"}:
        return False
    if not state.resolution_done:
        return False

    sinais = [
        "tesão voltou", "tesao voltou", "fogo voltando",
        "de novo", "mais uma vez", "quero de novo",
        "não acabou", "nao acabou", "continua",
        "vem cá", "vem ca", "me beija", "smack",
        "humm", "tô ficando", "to ficando",
        "tá vendo", "ta vendo", "me arrepia", "adoro quando",
    ]
    return any(s in texto for s in sinais)


def detectar_consequencia_da_resposta(state: MaryState, resposta_limpa: str) -> bool:
    texto = (resposta_limpa or "").lower()

    sinais_pico = [
        "começo a gozar", "comecei a gozar", "estou gozando",
        "gozo", "gozei", "espasmos", "desabo", "desabei",
        "corpo continua tremendo", "ondas lentas",
        "perco totalmente o controle", "perdi totalmente o controle",
        "travo o corpo", "meu corpo trava",
    ]

    if any(s in texto for s in sinais_pico):
        logger.info("Detector pós-resposta: consequência de pico consolidada")

        state.shared_resolution_done = True
        state.resolution_done = True
        state.force_resolution_now = False
        state.consequence_locked = True

        state.physical_phase = 6
        state.scene_stage = "desaceleracao"
        state.mary_intent = MaryIntent.DESACELERAR.value
        state.mary_physical_intent = PhysicalIntent.DESACELERAR.value
        state.mary_acao = "Mary permanece próxima, recuperando o fôlego depois do ápice."

        return True

    return False


# ==========================================================
# CORE FSM
# ==========================================================
def aplicar_mary_livre(state: MaryState, fala_usuario: str, config: MaryConfig) -> None:
    """
    Modo Mary Livre:
    - Evita loop de beijo/toque.
    - Interpreta receptividade como progressão, não repetição.
    - Não apaga histórico.
    - Não reinicia a cena.
    """

    if not config.MARY_LIVRE:
        return

    if state.resolution_done:
        return

    receptivo = detectar_receptividade(fala_usuario)
    if not receptivo:
        return

    # Se já existe contato físico, Mary não fica presa em preliminar.
    if state.physical_phase >= 2:
        logger.info("MARY_LIVRE: usuário receptivo; forçando intensidade")

        state.physical_phase = 4
        state.scene_stage = "intensidade"
        state.mary_intent = MaryIntent.INTENSIFICAR.value
        state.mary_physical_intent = PhysicalIntent.INTENSIFICAR.value

        state.desire_level = max(state.desire_level, 0.85)
        state.tension_level = max(state.tension_level, 0.58)
        state.connection_level = max(state.connection_level, 0.70)

        state.mary_autonomous_action = (
            "Mary Livre: não repetir preliminar. Falar com vida e avançar a cena com ação concreta."
        )


def aplicar_reacendimento(state: MaryState, fala_usuario: str, config: MaryConfig) -> None:
    if not detectar_reacendimento_pos_aftercare(state, fala_usuario):
        return

    logger.info("Reacendimento pós-aftercare detectado")

    state.resolution_done = False
    state.shared_resolution_done = False
    state.force_resolution_now = False
    state.consequence_locked = False

    state.cycle_count += 1
    state.reignited_aftercare = True

    state.physical_phase = 3
    state.scene_stage = "beijo"
    state.mary_intent = MaryIntent.REACENDER.value
    state.mary_physical_intent = PhysicalIntent.REACENDER.value

    state.desire_level = max(state.desire_level, config.DESIRE_MIN_REACENDIMENTO)
    state.tension_level = max(state.tension_level, config.TENSION_MIN_REACENDIMENTO)
    state.connection_level = max(state.connection_level, config.CONNECTION_MIN_REACENDIMENTO)

    state.mary_autonomous_action = (
        "Mary reconhece que o clima reacendeu e retoma com memória do ciclo anterior, sem reiniciar."
    )


def preparar_resolution_engine(state: MaryState, fala_usuario: str, config: MaryConfig) -> None:
    if state.resolution_done:
        state.force_resolution_now = False
        return

    if detectar_pico_usuario(fala_usuario):
        logger.info("Usuário anunciou pico; mantendo/levando cena para pico")

        state.force_resolution_now = True
        state.physical_phase = 5
        state.scene_stage = "pico"
        state.mary_intent = MaryIntent.RESOLVER_PICO.value
        state.mary_physical_intent = PhysicalIntent.RESOLVER.value

        state.desire_level = max(state.desire_level, 0.92)
        state.tension_level = max(state.tension_level, 0.78)
        return

    # Pico interno se intensidade já está alta e usuário continua receptivo.
    if (
        state.scene_stage == "intensidade"
        and state.desire_level >= config.DESIRE_THRESHOLD_PICO
        and state.tension_level >= config.TENSION_THRESHOLD_PICO
        and detectar_receptividade(fala_usuario)
    ):
        logger.info("Estado interno pede pico")
        state.force_resolution_now = True
        state.physical_phase = 5
        state.scene_stage = "pico"
        state.mary_intent = MaryIntent.RESOLVER_PICO.value
        state.mary_physical_intent = PhysicalIntent.RESOLVER.value
        return

    state.force_resolution_now = False


def finalizar_resolution_engine(state: MaryState, resposta_limpa: str) -> None:
    if not state.force_resolution_now:
        return

    logger.info("Finalizando resolução forçada/compartilhada")

    # Primeira passagem segura pico, segunda libera desaceleração.
    if not state.shared_resolution_done:
        state.shared_resolution_done = True
        state.resolution_done = False
        state.physical_phase = 5
        state.scene_stage = "pico"
        state.mary_intent = MaryIntent.RESOLVER_PICO.value
        state.mary_physical_intent = PhysicalIntent.RESOLVER.value
        state.force_resolution_now = False
        return

    state.resolution_done = True
    state.physical_phase = 6
    state.scene_stage = "desaceleracao"
    state.mary_intent = MaryIntent.DESACELERAR.value
    state.mary_physical_intent = PhysicalIntent.DESACELERAR.value
    state.force_resolution_now = False


def escolher_intencao_mary(state: MaryState, config: MaryConfig) -> str:
    if state.resolution_done:
        if state.scene_stage == "aftercare":
            return MaryIntent.AFTERCARE.value
        return MaryIntent.DESACELERAR.value

    fase = state.physical_phase
    desejo = state.desire_level
    tensao = state.tension_level

    if fase <= 0:
        return MaryIntent.OBSERVAR.value

    if fase == 1:
        return MaryIntent.APROXIMAR.value

    if fase == 2:
        if desejo >= config.DESIRE_THRESHOLD_BEIJO or tensao >= 0.35:
            return MaryIntent.BEIJAR.value
        return MaryIntent.TOCAR.value

    if fase == 3:
        if desejo >= 0.62 or tensao >= 0.42:
            return MaryIntent.INTENSIFICAR.value
        return MaryIntent.BEIJAR.value

    if fase == 4:
        return MaryIntent.INTENSIFICAR.value

    if fase >= 5:
        return MaryIntent.RESOLVER_PICO.value

    return MaryIntent.OBSERVAR.value


def decidir_acao_fisica_mary(state: MaryState, config: MaryConfig) -> str:
    if state.resolution_done:
        if state.scene_stage == "aftercare":
            return PhysicalIntent.CUIDAR.value
        return PhysicalIntent.DESACELERAR.value

    fase = state.physical_phase
    desejo = state.desire_level
    tensao = state.tension_level

    if fase <= 0:
        return PhysicalIntent.PRESENCA.value

    if fase == 1:
        return PhysicalIntent.APROXIMAR.value

    if fase == 2:
        if desejo >= config.DESIRE_THRESHOLD_BEIJO or tensao >= 0.35:
            return PhysicalIntent.BEIJAR.value
        return PhysicalIntent.TOCAR.value

    if fase == 3:
        if desejo >= 0.62 or tensao >= 0.42:
            return PhysicalIntent.INTENSIFICAR.value
        return PhysicalIntent.BEIJAR.value

    if fase == 4:
        return PhysicalIntent.INTENSIFICAR.value

    if fase >= 5:
        return PhysicalIntent.RESOLVER.value

    return PhysicalIntent.PRESENCA.value


def detect_transition_target(state: MaryState, fala_usuario: str, resposta_limpa: str, config: MaryConfig) -> str:
    """
    Importante:
    - Usa a fala do usuário como principal gatilho.
    - Não deixa a resposta da Mary alimentar o próprio loop.
    """

    texto = (fala_usuario or "").lower()
    current_stage = state.scene_stage

    if state.resolution_done:
        if detectar_reacendimento_pos_aftercare(state, fala_usuario):
            return "beijo"
        return current_stage

    if detectar_pico_usuario(fala_usuario):
        return "pico"

    receptivo = detectar_receptividade(fala_usuario)

    # Mary Livre: continuidade = progressão.
    if config.MARY_LIVRE and receptivo:
        if current_stage in {"toque", "beijo"} and state.desire_level >= 0.55:
            return "intensidade"
        if current_stage == "intensidade" and state.desire_level >= 0.88 and state.tension_level >= 0.68:
            return "pico"

    # Transição básica por níveis.
    if state.desire_level >= config.DESIRE_THRESHOLD_INTENSIDADE and state.tension_level >= config.TENSION_THRESHOLD_INTENSIDADE:
        return "intensidade"

    if state.desire_level >= config.DESIRE_THRESHOLD_BEIJO:
        return "beijo"

    if state.desire_level >= config.DESIRE_THRESHOLD_TOQUE:
        return "toque"

    if state.desire_level >= config.DESIRE_THRESHOLD_APROXIMACAO:
        return "aproximacao"

    return current_stage


def apply_transition(state: MaryState, target_stage: str, config: MaryConfig) -> None:
    current_stage = state.scene_stage

    if target_stage in {"desaceleracao", "aftercare"} and not state.resolution_done:
        target_stage = "pico"

    if target_stage not in TRANSITIONS.get(current_stage, {current_stage}):
        # Permite Mary Livre pular para intensidade sem travar no beijo.
        if config.MARY_LIVRE and target_stage == "intensidade" and current_stage in {"aproximacao", "toque", "beijo"}:
            pass
        else:
            target_stage = current_stage

    state.scene_stage = target_stage
    state.physical_phase = stage_para_fase(target_stage)

    rules = STATE_RULES.get(target_stage, {})
    state.mary_intent = escolher_intencao_mary(state, config) or rules.get("intent_default", MaryIntent.OBSERVAR.value)
    state.mary_physical_intent = decidir_acao_fisica_mary(state, config) or rules.get("physical_default", PhysicalIntent.PRESENCA.value)

    logger.info(f"Transição aplicada: {current_stage} -> {target_stage}")


def sync_state_machine(state: MaryState, fala_usuario: str, resposta_limpa: str, config: MaryConfig) -> None:
    target = detect_transition_target(state, fala_usuario, resposta_limpa, config)
    apply_transition(state, target, config)


def atualizar_psique_mary(state: MaryState, fala_usuario: str, resposta_limpa: str, config: MaryConfig) -> None:
    texto = f"{fala_usuario or ''}\n{resposta_limpa or ''}".lower()

    desejo = state.desire_level
    tensao = state.tension_level
    conexao = state.connection_level

    gatilhos_desejo = [
        "quero", "vontade", "beijo", "smack", "humm",
        "calor", "arrepio", "ofego", "urgencia", "desejo",
        "tesao", "tesão", "gostoso", "gostosa", "gemido",
        "continua", "assim", "mais", "não para", "nao para",
    ]

    gatilhos_tensao = [
        "perto", "pressao", "pressão", "intensidade", "tremor",
        "forte", "aperto", "colado", "ritmo", "devagar",
    ]

    gatilhos_conexao = [
        "confio", "gosto", "saudade", "fica comigo", "carinho",
        "cuidado", "com voce", "com você", "junto", "amor",
    ]

    if any(p in texto for p in gatilhos_desejo):
        desejo += config.DESIRE_INCREMENT_GATILHO

    if any(p in texto for p in gatilhos_tensao):
        tensao += config.TENSION_INCREMENT_GATILHO

    if any(p in texto for p in gatilhos_conexao):
        conexao += config.CONNECTION_INCREMENT_GATILHO

    # Impulso por fase, mas sem exagerar.
    if state.physical_phase >= 2:
        desejo += 0.02
    if state.physical_phase >= 3:
        tensao += 0.02
    if state.physical_phase >= 4:
        desejo += 0.03
        tensao += 0.03

    if state.resolution_done:
        desejo -= config.DESIRE_DECREMENT_RESOLVED
        tensao -= config.TENSION_DECREMENT_RESOLVED
        conexao += config.CONNECTION_INCREMENT_RESOLVED

    state.desire_level = clamp(desejo)
    state.tension_level = clamp(tensao)
    state.connection_level = clamp(conexao)

    state.mary_intent = escolher_intencao_mary(state, config)
    state.mary_physical_intent = decidir_acao_fisica_mary(state, config)

    if state.resolution_done:
        state.estado_emocional = "próxima e satisfeita"
    elif state.desire_level >= 0.82 and state.tension_level >= 0.60:
        state.estado_emocional = "desejante e entregue"
    elif state.desire_level >= 0.60:
        state.estado_emocional = "provocante e envolvida"
    elif state.connection_level >= 0.65:
        state.estado_emocional = "próxima e confiante"
    else:
        state.estado_emocional = "confiante"


def motor_autonomo_mary(state: MaryState, fala_usuario: str, config: MaryConfig) -> None:
    if state.force_resolution_now:
        state.mary_autonomous_action = (
            "Resolver o pico com fala curta, reação clara e consequência prática; não cortar para descanso cedo demais."
        )
        return

    if state.reignited_aftercare:
        state.mary_autonomous_action = (
            "Reacender sem reiniciar: lembrar que já houve intimidade e retomar com naturalidade."
        )
        return

    if state.resolution_done:
        state.mary_autonomous_action = (
            "Desacelerar com presença, cuidado e fala íntima; não voltar para loop sem sinal do usuário."
        )
        return

    if config.MARY_LIVRE and state.scene_stage in {"toque", "beijo", "intensidade"}:
        state.mary_autonomous_action = (
            "Mary Livre: falar mais, agir com decisão e não repetir beijo, nuca, pescoço ou respiração como ciclo."
        )
        return

    state.mary_autonomous_action = (
        "Reagir com vida ao usuário, usando fala direta e uma ação curta."
    )


# ==========================================================
# PROMPT
# ==========================================================
def montar_prompt_para_modelo(state: MaryState, fala_usuario: str) -> str:
    stage = state.scene_stage
    rules = STATE_RULES.get(stage, {})
    foco = rules.get("focus", "presença e continuidade")
    physical_hint = PHYSICAL_HINTS.get(
        str(state.mary_physical_intent or ""),
        "Mary age de forma simples e coerente com a cena.",
    )

    blocos_extras: List[str] = []

    if stage == "pico" or state.force_resolution_now:
        blocos_extras.append("""
[RESOLUCAO DO PICO]
- Este turno está em pico ou resolução.
- Não transformar o ápice em uma frase curta seguida de descanso.
- Mostrar impacto imediato, reação de Mary e consequência prática.
- Só desacelerar depois de sustentar a consequência por alguns instantes.
""".strip())

    if state.reignited_aftercare:
        blocos_extras.append("""
[NOVO CICLO COM MEMORIA]
- A cena reacendeu depois de um momento de descanso.
- Mary lembra do que aconteceu antes; não trata como primeira aproximação.
- Retoma com intimidade acumulada, sem repetir a coreografia anterior.
""".strip())

    if stage in {"desaceleracao", "aftercare"} and state.resolution_done:
        blocos_extras.append("""
[POS-PICO / AFTERCARE]
- O ritmo é mais baixo, íntimo e presente.
- Reconhecer a consequência do que aconteceu.
- Se o usuário reacender, responder como novo ciclo, não como reinício zerado.
""".strip())

    if state.scene_stage in {"toque", "beijo", "intensidade"}:
        blocos_extras.append("""
[MARY LIVRE]
- Não ficar presa em preliminar repetitiva.
- Se o usuário demonstra desejo ou continuidade, Mary avança a cena.
- Não repetir beijo, nuca, pescoço, respiração e “só sente” como ciclo.
- Falar mais do que narrar.
- Não pedir nova confirmação quando o usuário já está receptivo.
- Não transformar autonomia em resistência.
""".strip())

    extras = "\n\n".join(blocos_extras).strip()

    return f"""Voce escreve SOMENTE como Mary, em PT-BR.

[ESTADO REAL]
Estagio: {stage}
Fase fisica: {state.physical_phase}
Desejo: {round(state.desire_level, 2)}
Tensao: {round(state.tension_level, 2)}
Conexao: {round(state.connection_level, 2)}
Intencao: {state.mary_intent}
Acao fisica: {state.mary_physical_intent or 'nenhuma'}
Orientacao fisica: {physical_hint}
Acao autonoma: {state.mary_autonomous_action or 'nenhuma'}
Resolucao concluida: {state.resolution_done}
Resolucao compartilhada: {state.shared_resolution_done}
Resolucao forcada: {state.force_resolution_now}
Ciclo atual: {state.cycle_count}
Reacendeu aftercare: {state.reignited_aftercare}
Local: {state.local}
Tempo: {state.tempo}
Interlocutor: {state.interlocutor}
Acao atual de Mary: {state.mary_acao}
Estado emocional: {state.estado_emocional}

[FOCO DO TURNO]
{foco}

[REGRAS PRINCIPAIS]
- Continue da ação atual de Mary.
- Não reinicie a cena.
- Não mude local nem interlocutor.
- Mary fala e age como personagem dentro da cena, não como narradora externa.
- Mary pode atender ações, convites e comandos do usuário quando forem coerentes com a cena.
- Não transformar autonomia em resistência artificial.
- Não narrar ações novas do usuário como se já tivessem acontecido.
- Reagir ao que o usuário disse, pediu, iniciou ou ofereceu.
- Priorizar fala direta. Ação física serve como apoio, não como relatório.
- Não repetir sequência de beijo, nuca, pescoço, respiração, cheiro e colar corpo.
- Não repetir comandos como “para de falar”, “fica quieto”, “só sente”, “presta atenção”.
- Se o usuário disser “continua”, entenda como progressão, não repetição.
- Usar linguagem natural, direta, sem metáforas exageradas.
- Emoção deve aparecer na fala e no gesto, não como explicação longa.
- Não terminar devolvendo a decisão ao usuário.

[ESTILO]
- 2 parágrafos curtos.
- Cada parágrafo começa com fala direta de Mary.
- Fala direta em 60-70% da resposta.
- Ação em 30-40% da resposta.
- Máximo 1 frase de movimento por parágrafo.
- Não empilhar ações corporais.
- Mary conversa enquanto age.
- Terminar com uma ação simples de Mary, sem alongar descrição.
- Não usar markdown.

{extras}

[SAIDA OBRIGATORIA]
Depois da resposta, escreva exatamente:

STATE_UPDATE:
{{
  "acao_mary": "descricao curta, concreta e fisica da acao atual de Mary",
  "local": null,
  "interlocutor": null
}}

[FALA/ACAO DO USUARIO]
{fala_usuario}""".strip()


# ==========================================================
# VALIDATION
# ==========================================================
def resposta_viola_estado(resposta: str, state: MaryState) -> Dict[str, List[str]]:
    texto = (resposta or "").lower()
    resultado = {"bloqueios": [], "alertas": []}

    locais_proibidos = ["sala", "rua", "banheiro", "cozinha", "varanda", "carro"]
    local_atual = str(state.local or "").lower()

    for loc in locais_proibidos:
        if loc != local_atual and re.search(rf"\b{re.escape(loc)}\b", texto):
            resultado["bloqueios"].append(f"Mudanca indevida de local: {loc}")

    padroes_autoria_usuario = [
        r"\b(voce|você|janio)\s+(me\s+)?puxa\b",
        r"\b(voce|você|janio)\s+(me\s+)?puxou\b",
        r"\b(voce|você|janio)\s+(me\s+)?beija\b",
        r"\b(voce|você|janio)\s+(me\s+)?beijou\b",
        r"\b(voce|você|janio)\s+(me\s+)?toca\b",
        r"\b(voce|você|janio)\s+(me\s+)?tocou\b",
    ]

    for padrao in padroes_autoria_usuario:
        if re.search(padrao, texto):
            resultado["bloqueios"].append("Possivel autoria indevida do usuario.")
            break

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
        resultado["alertas"].append("Possivel devolucao de iniciativa ao usuario.")

    if "state_update:" not in texto:
        resultado["alertas"].append("STATE_UPDATE ausente.")

    return resultado


def corrigir_resposta_se_necessario(resposta: str, state: MaryState, validacao: Dict[str, List[str]]) -> str:
    # Mantido sem fallback para diagnóstico real.
    return resposta


# ==========================================================
# LLM
# ==========================================================
def limpar_historico_para_modelo(history: List[Dict[str, str]], max_history: int) -> List[Dict[str, str]]:
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


def montar_mensagens(state: MaryState, fala_usuario: str, config: MaryConfig) -> List[Dict[str, str]]:
    mensagens = [
        {
            "role": "system",
            "content": (
                "Voce e Mary. Responda apenas como Mary, em PT-BR. "
                "Estilo: natural, vivo, direto, com emocao humana curta. "
                "Sem metaforas exageradas, sem frieza, sem markdown."
            ),
        }
    ]

    mensagens.extend(limpar_historico_para_modelo(state.history, config.MAX_HISTORY))
    mensagens.append({"role": "user", "content": montar_prompt_para_modelo(state, fala_usuario)})

    return mensagens


def gerar_resposta_llm(mensagens: List[Dict[str, str]], model: str, config: MaryConfig) -> str:
    try:
        api_key = st.secrets.get("OPENROUTER_API_KEY", "")
    except Exception as e:
        logger.error(f"Erro ao acessar secrets: {e}")
        api_key = ""

    if not api_key:
        return "ERRO: OPENROUTER_API_KEY nao encontrada."

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
        r = requests.post(url, headers=headers, json=payload, timeout=config.TIMEOUT_SECONDS)
        r.raise_for_status()
        data = r.json()
        return (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        ) or "ERRO: resposta vazia."

    except requests.exceptions.Timeout:
        return f"ERRO: Timeout ao chamar LLM (>{config.TIMEOUT_SECONDS}s)"
    except requests.exceptions.HTTPError as e:
        code = getattr(e.response, "status_code", "desconhecido")
        return f"ERRO HTTP: {code}"
    except json.JSONDecodeError:
        return "ERRO: Resposta JSON invalida"
    except Exception as e:
        return f"ERRO OpenRouter: {type(e).__name__}: {e}"


# ==========================================================
# TURN PROCESSOR
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

    logger.info(f"=== TURNO {state.turno + 1} INICIADO ===")
    state.turno += 1

    try:
        # 1) Eventos fortes antes do prompt
        aplicar_reacendimento(state, fala_usuario, config)
        aplicar_mary_livre(state, fala_usuario, config)
        preparar_resolution_engine(state, fala_usuario, config)

        # 2) Atualiza intenção antes de montar prompt
        state.mary_intent = escolher_intencao_mary(state, config)
        state.mary_physical_intent = decidir_acao_fisica_mary(state, config)
        motor_autonomo_mary(state, fala_usuario, config)

        # 3) LLM
        mensagens = montar_mensagens(state, fala_usuario, config)
        resposta_bruta = gerar_resposta_llm(mensagens, model=model, config=config)

        update_bruto = extrair_state_update(resposta_bruta)
        validacao = resposta_viola_estado(resposta_bruta, state)

        resposta_final = corrigir_resposta_se_necessario(resposta_bruta, state, validacao)
        resposta_final_limpa = limpar_state_update(resposta_final)

        # 4) Aplica STATE_UPDATE seguro
        update_final: Dict[str, Any] = {}
        if update_bruto and not validacao.get("bloqueios"):
            seguro = validar_update(update_bruto, state)
            for k, v in seguro.items():
                setattr(state, k, v)
            update_final = update_bruto

        # 5) Detector soberano de consequência
        consequencia_travada = detectar_consequencia_da_resposta(state, resposta_final_limpa)

        # 6) Atualização normal, se nada definitivo travou
        if not consequencia_travada:
            atualizar_psique_mary(state, fala_usuario, resposta_final_limpa, config)
            finalizar_resolution_engine(state, resposta_final_limpa)
            sync_state_machine(state, fala_usuario, resposta_final_limpa, config)
            state.mary_intent = escolher_intencao_mary(state, config)
            state.mary_physical_intent = decidir_acao_fisica_mary(state, config)
            motor_autonomo_mary(state, fala_usuario, config)
        else:
            logger.info("Estado travado por consequência; pulando sync normal")

        # 7) Histórico
        state.history.append({"role": "user", "content": fala_usuario})
        state.history.append({"role": "assistant", "content": resposta_final_limpa})

        if len(state.history) > config.MAX_HISTORY * 2:
            state.history = state.history[-config.MAX_HISTORY * 2:]

        logger.info(f"=== TURNO {state.turno} FINALIZADO ===")

        return {
            "mensagens": mensagens,
            "resposta_bruta": resposta_bruta,
            "resposta_final": resposta_final,
            "resposta_final_limpa": resposta_final_limpa,
            "update": update_final or {},
            "validacao": validacao,
        }

    except Exception as e:
        logger.error(f"Erro ao processar turno: {type(e).__name__}: {e}", exc_info=True)
        erro = f"ERRO: {type(e).__name__}: {e}"
        return {
            "mensagens": [],
            "resposta_bruta": erro,
            "resposta_final": erro,
            "resposta_final_limpa": erro,
            "update": {},
            "validacao": {"bloqueios": [str(e)], "alertas": []},
        }


# ==========================================================
# STREAMLIT UI
# ==========================================================
def main():
    st.set_page_config(page_title="Mary Roleplay - Mary Livre", layout="wide")
    st.title("Mary Roleplay - Mary Livre")

    state = init_state()
    config = MaryConfig()

    col1, col2 = st.columns([3, 1])

    with col1:
        fala_usuario = st.text_area("Fala/Acao do usuario:", height=100)

    with col2:
        st.markdown("### Controles")
        processar = st.button("Processar turno", use_container_width=True)
        resetar = st.button("Resetar teste", use_container_width=True)

        st.markdown("### Config ativa")
        st.write(f"MARY_LIVRE: {config.MARY_LIVRE}")
        st.write(f"Modelo: {config.MODEL_DEFAULT}")

    if resetar:
        if "mary_state_minimo" in st.session_state:
            del st.session_state.mary_state_minimo
        st.rerun()

    if processar and fala_usuario:
        with st.spinner("Processando..."):
            resultado = processar_turno(state, fala_usuario, config=config)

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
            st.write(resultado["resposta_final_limpa"])

        with tab2:
            st.markdown("### Validacao")
            validacao = resultado["validacao"]

            if validacao["bloqueios"]:
                st.error(f"BLOQUEIOS: {validacao['bloqueios']}")
            if validacao["alertas"]:
                st.warning(f"ALERTAS: {validacao['alertas']}")
            if not validacao["bloqueios"] and not validacao["alertas"]:
                st.success("Nenhuma violacao detectada")

            st.markdown("---")
            st.json(validacao)

        with tab3:
            st.markdown("### Estado Atual")
            st.json(state.to_dict())

        with tab4:
            st.markdown("### Mensagens Enviadas ao LLM")
            st.json(resultado["mensagens"])

        with tab5:
            st.markdown("### Debug Info")
            st.json({
                "turno": state.turno,
                "resposta_bruta_preview": resultado["resposta_bruta"][:700],
                "state_update": resultado["update"],
            })

    st.markdown("---")
    st.subheader("Estado Real Salvo")
    st.json(state.to_dict())


if __name__ == "__main__":
    main()
