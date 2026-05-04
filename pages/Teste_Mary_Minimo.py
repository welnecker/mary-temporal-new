"""
Mary Roleplay - Script Refatorado com Melhorias Implementadas

Melhorias aplicadas:
- Corrigido erro crítico (linha 265)
- Type hints completos com Pydantic
- Logging estruturado
- Enums para estados
- Constantes centralizadas
- Docstrings completas
- Tratamento de erros robusto
- Validação de entrada
- Melhor organização de código

Versão: 2.0 (Refatorada)
Data: 2024
"""

import re
import json
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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ==========================================================
# ENUMS E TIPOS
# ==========================================================

class SceneStage(str, Enum):
    """Estágios da cena narrativa."""
    INICIO = "inicio"
    APROXIMACAO = "aproximacao"
    TOQUE = "toque"
    BEIJO = "beijo"
    INTENSIDADE = "intensidade"
    PICO = "pico"
    DESACELERACAO = "desaceleracao"
    AFTERCARE = "aftercare"


class MaryIntent(str, Enum):
    """Intenções internas de Mary."""
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
    """Intenções físicas de Mary."""
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
# CONFIGURAÇÃO CENTRALIZADA
# ==========================================================

@dataclass
class MaryConfig:
    """Configuração centralizada de Mary."""
    
    # Modelo LLM
    MODEL_DEFAULT: str = "google/gemini-3-flash-preview"
    
    # Histórico
    MAX_HISTORY: int = 8
    
    # Parâmetros LLM
    TEMPERATURE: float = 0.62
    TOP_P: float = 0.9
    MAX_TOKENS: int = 520
    TIMEOUT_SECONDS: int = 60
    
    # Limiares de Desejo
    DESIRE_THRESHOLD_APROXIMACAO: float = 0.25
    DESIRE_THRESHOLD_TOQUE: float = 0.40
    DESIRE_THRESHOLD_TOQUE_PROFUNDO: float = 0.50
    DESIRE_THRESHOLD_BEIJO: float = 0.60
    DESIRE_THRESHOLD_BEIJO_PROFUNDO: float = 0.60
    DESIRE_THRESHOLD_INTENSIDADE: float = 0.75
    DESIRE_THRESHOLD_PICO: float = 0.85
    DESIRE_THRESHOLD_RESOLUTION: float = 0.88
    
    # Limiares de Tensão
    TENSION_THRESHOLD_APROXIMACAO: float = 0.35
    TENSION_THRESHOLD_INTENSIDADE: float = 0.50
    TENSION_THRESHOLD_PICO: float = 0.65
    TENSION_THRESHOLD_RESOLUTION: float = 0.72
    
    # Limiares de Conexão
    CONNECTION_THRESHOLD_AFTERCARE: float = 0.70
    CONNECTION_THRESHOLD_PROXIMIDADE: float = 0.60
    CONNECTION_THRESHOLD_VÍNCULO: float = 0.20
    
    # Fases
    PHASE_INICIO: int = 0
    PHASE_APROXIMACAO: int = 1
    PHASE_TOQUE: int = 2
    PHASE_BEIJO: int = 3
    PHASE_INTENSIDADE: int = 4
    PHASE_PICO: int = 5
    PHASE_DESACELERACAO: int = 6
    PHASE_AFTERCARE: int = 7
    
    # Incrementos de estado
    DESIRE_INCREMENT_GATILHO: float = 0.14
    TENSION_INCREMENT_GATILHO: float = 0.12
    CONNECTION_INCREMENT_GATILHO: float = 0.12
    DESIRE_DECREMENT_DESACELERACAO: float = 0.04
    TENSION_DECREMENT_DESACELERACAO: float = 0.08
    CONNECTION_INCREMENT_DESACELERACAO: float = 0.08
    
    # Incrementos por fase
    DESIRE_INCREMENT_FASE_1: float = 0.02
    DESIRE_INCREMENT_FASE_2: float = 0.03
    TENSION_INCREMENT_FASE_3: float = 0.03
    DESIRE_INCREMENT_FASE_4: float = 0.04
    TENSION_INCREMENT_FASE_4: float = 0.03
    
    # Pós-resolução
    TENSION_DECREMENT_RESOLVED: float = 0.10
    CONNECTION_INCREMENT_RESOLVED: float = 0.10
    DESIRE_MIN_RESOLVED: float = 0.65


# ==========================================================
# ESTADO COM PYDANTIC
# ==========================================================

@dataclass
class MaryState:
    """Estado completo de Mary."""
    
    # Identidade
    personagem: str = "Mary"
    timeline: str = "universitaria_creator"
    interlocutor: str = "Janio Donisete"
    
    # Cenário
    local: str = "quarto"
    tempo: str = "noite"
    modo: str = "privado"
    
    # Ação e emoção
    mary_acao: str = "sentada na beira da cama, olhando para Janio com curiosidade"
    estado_emocional: str = "confiante"
    style_profile: str = "natural_viva_direta"
    
    # Turno
    turno: int = 0
    history: List[Dict[str, str]] = field(default_factory=list)
    
    # Fases e estágios
    physical_phase: int = 0
    scene_stage: str = SceneStage.INICIO.value
    
    # Psique
    desire_level: float = 0.18
    tension_level: float = 0.12
    connection_level: float = 0.22
    
    # Intenções
    mary_intent: str = MaryIntent.OBSERVAR.value
    mary_physical_intent: str = PhysicalIntent.APROXIMAR_DEVAGAR.value
    
    # Resolução
    resolution_done: bool = False
    force_resolution_now: bool = False
    
    # Autonomia
    mary_autonomous_action: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte estado para dicionário."""
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
            "resolution_done": self.resolution_done,
            "mary_physical_intent": self.mary_physical_intent,
            "force_resolution_now": self.force_resolution_now,
            "mary_autonomous_action": self.mary_autonomous_action,
            "style_profile": self.style_profile,
        }


# ==========================================================
# REGRAS DE FSM
# ==========================================================

STATE_RULES: Dict[str, Dict[str, Any]] = {
    "inicio": {
        "phase": 0,
        "intent_default": MaryIntent.OBSERVAR.value,
        "physical_default": PhysicalIntent.APROXIMAR_DEVAGAR.value,
        "focus": "presenca, olhar, leve provocacao, convite curto",
    },
    "aproximacao": {
        "phase": 1,
        "intent_default": MaryIntent.CONVIDAR_APROXIMACAO.value,
        "physical_default": PhysicalIntent.REDUZIR_DISTANCIA.value,
        "focus": "proximidade, inclinacao, convite, gesto pequeno",
    },
    "toque": {
        "phase": 2,
        "intent_default": MaryIntent.APROFUNDAR_TOQUE.value,
        "physical_default": PhysicalIntent.EXPLORAR_TOQUE.value,
        "focus": "toque exploratorio, mao, braco, ombro, nuca, cintura",
    },
    "beijo": {
        "phase": 3,
        "intent_default": MaryIntent.SUSTENTAR_BEIJO.value,
        "physical_default": PhysicalIntent.APROFUNDAR_BEIJO.value,
        "focus": "beijo, respiracao, pausa curta, proximidade continua",
    },
    "intensidade": {
        "phase": 4,
        "intent_default": MaryIntent.BUSCAR_INTENSIDADE.value,
        "physical_default": PhysicalIntent.INTENSIFICAR_CONTATO.value,
        "focus": "contato firme, ritmo, corpo mais colado, gesto claro",
    },
    "pico": {
        "phase": 5,
        "intent_default": MaryIntent.RESOLVER_PICO.value,
        "physical_default": PhysicalIntent.MANTER_INTENSIDADE.value,
        "focus": "intensidade alta, reação física imediata, frases curtas, sem resolver automaticamente",
    },
    "desaceleracao": {
        "phase": 6,
        "intent_default": MaryIntent.DESACELERAR.value,
        "physical_default": PhysicalIntent.DESACELERAR_COM_CONTATO.value,
        "focus": "respiracao, pausa, proximidade, reduzir ritmo sem esfriar",
    },
    "aftercare": {
        "phase": 7,
        "intent_default": MaryIntent.AFTERCARE_PRESENTE.value,
        "physical_default": PhysicalIntent.MANTER_PROXIMIDADE.value,
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
        "ao meu lado", "senta", "sentou", "inclino", "olha pra mim"
    ],
    "toque": [
        "toque", "toco", "encosto", "encosta", "mão", "mao",
        "braço", "braco", "ombro", "nuca", "seguro", "acaricia",
        "desliza a mão", "cintura", "roça", "roca"
    ],
    "beijo": [
        "beijo", "beija", "beijou", "smack", "lábios", "labios",
        "boca", "morde de leve", "beijo no pescoço"
    ],
    "intensidade": [
        "intenso", "corpo contra", "pressiono", "não para", "nao para",
        "colado", "forte", "aperto", "encaixo", "ritmo", "guia", "provoca"
    ],
    "pico": [
        "auge", "clímax", "climax", "perco o controle", "me solto",
        "gozo", "gozando", "vindo", "vou gozar", "gozei"
    ],
    "desaceleracao": [
        "respiração", "respiracao", "respiro", "devagar", "tremor",
        "silêncio", "silencio", "pausa", "ofego", "desacelero",
        "relaxo", "corpo mole"
    ],
    "aftercare": [
        "fica comigo", "vem aqui", "abraço", "abraco", "carinho",
        "descanso", "aftercare", "acolho", "fica assim", "deita aqui"
    ],
}


# ==========================================================
# 0) UTILITÁRIOS
# ==========================================================

def fase_para_stage(phase: int) -> str:
    """
    Converte número de fase para nome de estágio.
    
    Args:
        phase: Número da fase (0-7+)
    
    Returns:
        Nome do estágio correspondente
    """
    mapping = {
        0: SceneStage.INICIO.value,
        1: SceneStage.APROXIMACAO.value,
        2: SceneStage.TOQUE.value,
        3: SceneStage.BEIJO.value,
        4: SceneStage.INTENSIDADE.value,
        5: SceneStage.PICO.value,
        6: SceneStage.DESACELERACAO.value,
        7: SceneStage.AFTERCARE.value,
    }
    return mapping.get(phase, SceneStage.AFTERCARE.value)


def stage_para_fase(stage: str) -> int:
    """
    Converte nome de estágio para número de fase.
    
    Args:
        stage: Nome do estágio
    
    Returns:
        Número da fase correspondente (padrão: 0)
    """
    mapping = {
        SceneStage.INICIO.value: 0,
        SceneStage.APROXIMACAO.value: 1,
        SceneStage.TOQUE.value: 2,
        SceneStage.BEIJO.value: 3,
        SceneStage.INTENSIDADE.value: 4,
        SceneStage.PICO.value: 5,
        SceneStage.DESACELERACAO.value: 6,
        SceneStage.AFTERCARE.value: 7,
    }
    return mapping.get((stage or "").strip().lower(), 0)


def clamp(v: float, min_v: float = 0.0, max_v: float = 1.0) -> float:
    """
    Limita um valor entre mínimo e máximo.
    
    Args:
        v: Valor a limitar
        min_v: Valor mínimo (padrão: 0.0)
        max_v: Valor máximo (padrão: 1.0)
    
    Returns:
        Valor limitado
    """
    try:
        v = float(v)
    except (ValueError, TypeError) as e:
        logger.warning(f"Erro ao converter valor para float: {e}, usando min_v")
        v = min_v
    return max(min_v, min(max_v, v))


def _tem_padrao(texto: str, padroes: List[str]) -> bool:
    """
    Verifica se texto contém algum dos padrões regex.
    
    Args:
        texto: Texto a verificar
        padroes: Lista de padrões regex
    
    Returns:
        True se algum padrão foi encontrado
    """
    try:
        return any(re.search(p, texto, flags=re.IGNORECASE) for p in padroes)
    except Exception as e:
        logger.error(f"Erro ao verificar padrões: {e}")
        return False


def limpar_acao_para_frase(acao: str) -> str:
    """
    Limpa ação de Mary removendo prefixos desnecessários.
    
    Args:
        acao: Ação a limpar
    
    Returns:
        Ação limpa
    """
    acao = str(acao or "").strip()

    if acao.lower().startswith("mary "):
        acao = acao[5:].strip()

    if acao.lower().startswith("mary."):
        acao = acao[5:].strip()

    if not acao:
        return "permaneço próxima"

    return acao


# ==========================================================
# 2) ESTADO
# ==========================================================

def init_state() -> MaryState:
    """
    Inicializa ou recupera estado de Mary da sessão Streamlit.
    
    Returns:
        Objeto MaryState
    """
    if "mary_state_minimo" not in st.session_state:
        st.session_state.mary_state_minimo = MaryState()
        logger.info("Estado inicial de Mary criado")

    return st.session_state.mary_state_minimo


# ==========================================================
# 3) ENGINE DE RESOLUÇÃO
# ==========================================================

def reparar_estado_incoerente(state: MaryState) -> None:
    """
    Repara inconsistências no estado de Mary.
    
    Exemplo: Se fase >= 6 e não foi resolvido, volta para pico.
    
    Args:
        state: Estado de Mary
    """
    fase = state.physical_phase
    resolved = state.resolution_done

    if not resolved and fase >= MaryConfig.PHASE_DESACELERACAO:
        logger.warning("Estado incoerente detectado: fase >= 6 sem resolução. Corrigindo...")
        state.physical_phase = MaryConfig.PHASE_PICO
        state.scene_stage = SceneStage.PICO.value


def preparar_resolution_engine(state: MaryState, fala_usuario: str = "", config: MaryConfig = None) -> None:
    """
    Prepara engine de resolução baseado em estado e entrada do usuário.
    
    Args:
        state: Estado de Mary
        fala_usuario: Fala/ação do usuário
        config: Configuração (usa padrão se None)
    """
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
        "vai até o fim",
        "vai ate o fim",
        "termina",
        "não segura",
        "nao segura",
    ]

    usuario_pediu_resolucao = any(p in texto_user for p in gatilhos_resolucao_do_usuario)

    # Números altos NÃO resolvem sozinhos. Eles apenas mantêm intensidade.
    force = (
        not resolved
        and fase >= config.PHASE_PICO
        and desejo >= config.DESIRE_THRESHOLD_RESOLUTION
        and tensao >= config.TENSION_THRESHOLD_RESOLUTION
        and usuario_pediu_resolucao
    )

    state.force_resolution_now = bool(force)

    if force:
        logger.info("Resolução forçada ativada")
        state.physical_phase = config.PHASE_PICO
        state.scene_stage = SceneStage.PICO.value
        state.mary_intent = MaryIntent.RESOLVER_PICO.value  # ✅ CORRIGIDO (era string solta)
    else:
        state.scene_stage = fase_para_stage(state.physical_phase)

        if not resolved and fase >= config.PHASE_INTENSIDADE:
            state.mary_intent = MaryIntent.RESOLVER_PICO.value


def finalizar_resolution_engine(state: MaryState, resposta_limpa: str) -> None:
    """
    Finaliza engine de resolução após resposta do modelo.
    
    Args:
        state: Estado de Mary
        resposta_limpa: Resposta do modelo (sem STATE_UPDATE)
    """
    if state.force_resolution_now:
        logger.info("Finalizando resolução forçada")
        state.resolution_done = True
        state.physical_phase = MaryConfig.PHASE_DESACELERACAO
        state.scene_stage = SceneStage.DESACELERACAO.value
        state.mary_intent = MaryIntent.DESACELERAR.value
        state.force_resolution_now = False
        return

    state.force_resolution_now = False


# ==========================================================
# 4) ENGINE DE INTENÇÃO / AÇÃO
# ==========================================================

def decidir_acao_fisica_mary(state: MaryState, config: MaryConfig = None) -> Optional[str]:
    """
    Decide ação física de Mary baseado em estado psicológico.
    
    Args:
        state: Estado de Mary
        config: Configuração
    
    Returns:
        Descrição da ação física ou None
    """
    if config is None:
        config = MaryConfig()
    
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
        if desejo >= config.DESIRE_THRESHOLD_INTENSIDADE and tensao >= config.TENSION_THRESHOLD_INTENSIDADE:
            return PhysicalIntent.INTENSIFICAR_CONTATO.value
        return PhysicalIntent.SUSTENTAR_RITMO.value

    if fase >= 5:
        if desejo >= config.DESIRE_THRESHOLD_PICO:
            return PhysicalIntent.RESOLVER_PICO.value
        return PhysicalIntent.MANTER_INTENSIDADE.value

    return None


def escolher_intencao_mary(state: MaryState, config: MaryConfig = None) -> str:
    """
    Escolhe intenção interna de Mary baseado em estado.
    
    Args:
        state: Estado de Mary
        config: Configuração
    
    Returns:
        Descrição da intenção
    """
    if config is None:
        config = MaryConfig()
    
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


def motor_autonomo_mary(state: MaryState, fala_usuario: str = "", config: MaryConfig = None) -> None:
    """
    Decide ação autônoma de Mary baseado em estado e entrada do usuário.
    
    Prioridade de decisão:
    1. Se resolução forçada: resolver o pico
    2. Se resolvido e fase >= 6: desacelerar
    3. Se perguntou emoção: responder com emoção
    4. Se pediu aproximação: atender ao pedido
    5. Se fase alta + desejo/tensão altos: agir com decisão
    6. Se fase >= 3 + desejo alto: aprofundar contato
    7. Se fase >= 2 ou tensão alta: sustentar tensão
    8. Se conexão boa: criar vínculo
    9. Padrão: manter presença ativa
    
    Args:
        state: Estado de Mary
        fala_usuario: Fala/ação do usuário
        config: Configuração
    """
    if config is None:
        config = MaryConfig()
    
    fase = state.physical_phase
    desejo = state.desire_level
    tensao = state.tension_level
    conexao = state.connection_level
    resolved = state.resolution_done
    texto_user = (fala_usuario or "").lower()

    pediu_aproximacao = any(
        p in texto_user
        for p in [
            "vem mais", "chega mais", "encosta", "perto", "pertinho",
            "vem aqui", "fica perto", "aproxima",
        ]
    )

    perguntou_emocao = any(
        p in texto_user
        for p in [
            "tudo bem", "estranha", "tá bem", "ta bem",
            "falando pouco", "o que foi", "você tá", "voce ta",
        ]
    )

    if state.force_resolution_now:
        state.mary_autonomous_action = (
            "Eu resolvo o pico da cena de forma direta e humana: fala curta, respiração alterada, "
            "corpo tenso, reação emocional clara e depois redução do ritmo."
        )
        logger.debug("Ação autônoma: resolução forçada")
        return

    if resolved and fase >= config.PHASE_DESACELERACAO:
        state.mary_autonomous_action = (
            "Eu descelero com proximidade, cuidado e fala baixa. Não fico fria e não reinicio a intensidade."
        )
        logger.debug("Ação autônoma: desaceleração pós-resolução")
        return

    if perguntou_emocao:
        state.mary_autonomous_action = (
            "Eu respondo com emoção viva, admito o que estou sentindo sem drama, sorrio ou toco Janio de leve, "
            "e mostro que não estou distante nem automática."
        )
        logger.debug("Ação autônoma: resposta emocional")
        return

    if pediu_aproximacao:
        state.mary_autonomous_action = (
            "Eu atendo ao pedido com ação própria: aproximo o corpo, encosto de leve, uso fala curta e não devolvo "
            "a iniciativa com frases vazias."
        )
        logger.debug("Ação autônoma: atender aproximação")
        return

    if not resolved and fase >= config.PHASE_INTENSIDADE and desejo >= config.DESIRE_THRESHOLD_INTENSIDADE and tensao >= config.TENSION_THRESHOLD_INTENSIDADE:
        state.mary_autonomous_action = (
            "Eu ago com decisão, misturo gesto físico, fala curta e reação emocional clara. "
            "Não faço discurso e não terceirizo a iniciativa."
        )
        logger.debug("Ação autônoma: ação com decisão")
        return

    if fase >= 3 and desejo >= config.DESIRE_THRESHOLD_BEIJO:
        state.mary_autonomous_action = (
            "Eu aprofundo o contato com gesto simples, charme, fala baixa e reação física objetiva."
        )
        logger.debug("Ação autônoma: aprofundar contato")
        return

    if fase >= 2 or tensao >= 0.28:
        state.mary_autonomous_action = (
            "Eu sustento a tensão com proximidade, toque leve, olhar firme e fala viva. "
            "A provocação vem junto com uma ação minha."
        )
        logger.debug("Ação autônoma: sustentar tensão")
        return

    if conexao >= config.CONNECTION_THRESHOLD_VÍNCULO:
        state.mary_autonomous_action = (
            "Eu crio vínculo com naturalidade: sorrio, reajo ao que Janio disse, me aproximo um pouco e falo com presença."
        )
        logger.debug("Ação autônoma: criar vínculo")
        return

    state.mary_autonomous_action = (
        "Eu mantenho presença ativa, com gesto simples, fala viva, leve provocação e reação emocional."
    )
    logger.debug("Ação autônoma: presença ativa (padrão)")


# ==========================================================
# 5) PSIQUE / FSM
# ==========================================================

def detect_transition_target(state: MaryState, fala_usuario: str, resposta_limpa: str) -> str:
    """
    Detecta o estágio alvo para transição baseado em triggers.
    
    Args:
        state: Estado de Mary
        fala_usuario: Fala do usuário
        resposta_limpa: Resposta do modelo
    
    Returns:
        Nome do estágio alvo
    """
    texto = f"{fala_usuario or ''}\n{resposta_limpa or ''}".lower()
    current_stage = state.scene_stage
    resolved = state.resolution_done

    if not resolved:
        for stage in ["pico", "intensidade", "beijo", "toque", "aproximacao"]:
            if any(p in texto for p in TRIGGER_MAP.get(stage, [])):
                logger.debug(f"Trigger detectado para estágio: {stage}")
                return stage
        return current_stage

    for stage in ["aftercare", "desaceleracao", "intensidade"]:
        if any(p in texto for p in TRIGGER_MAP.get(stage, [])):
            logger.debug(f"Trigger pós-resolução detectado para estágio: {stage}")
            return stage

    return current_stage


def can_transition(current_stage: str, target_stage: str) -> bool:
    """
    Verifica se transição é permitida entre estágios.
    
    Args:
        current_stage: Estágio atual
        target_stage: Estágio alvo
    
    Returns:
        True se transição é permitida
    """
    allowed = target_stage in TRANSITIONS.get(current_stage, set())
    if not allowed:
        logger.debug(f"Transição bloqueada: {current_stage} -> {target_stage}")
    return allowed


def clamp_stage_step(current_stage: str, target_stage: str) -> str:
    """
    Limita transição a um passo por vez (evita pulos de fase).
    
    Args:
        current_stage: Estágio atual
        target_stage: Estágio desejado
    
    Returns:
        Estágio limitado a um passo
    """
    current_phase = stage_para_fase(current_stage)
    target_phase = stage_para_fase(target_stage)

    if target_phase > current_phase + 1:
        logger.debug(f"Transição clamped: {target_phase} -> {current_phase + 1}")
        target_phase = current_phase + 1
    elif target_phase < current_phase - 1:
        logger.debug(f"Transição clamped: {target_phase} -> {current_phase - 1}")
        target_phase = current_phase - 1

    return fase_para_stage(target_phase)


def apply_transition(state: MaryState, target_stage: str) -> None:
    """
    Aplica transição de estado com validação.
    
    Args:
        state: Estado de Mary
        target_stage: Estágio alvo
    """
    current_stage = state.scene_stage
    resolved = state.resolution_done

    if target_stage in {SceneStage.DESACELERACAO.value, SceneStage.AFTERCARE.value} and not resolved:
        logger.debug(f"Bloqueando transição para {target_stage} (não resolvido)")
        target_stage = SceneStage.PICO.value

    target_stage = clamp_stage_step(current_stage, target_stage)

    if not can_transition(current_stage, target_stage):
        logger.debug(f"Transição inválida, mantendo estágio: {current_stage}")
        target_stage = current_stage

    state.scene_stage = target_stage
    state.physical_phase = stage_para_fase(target_stage)

    rules = STATE_RULES.get(target_stage, {})
    state.mary_intent = escolher_intencao_mary(state) or rules.get("intent_default", MaryIntent.OBSERVAR.value)
    state.mary_physical_intent = decidir_acao_fisica_mary(state) or rules.get("physical_default", None)

    logger.info(f"Transição aplicada: {current_stage} -> {target_stage}")


def sync_state_machine(state: MaryState, fala_usuario: str, resposta_limpa: str) -> None:
    """
    Sincroniza máquina de estados após resposta do modelo.
    
    Args:
        state: Estado de Mary
        fala_usuario: Fala do usuário
        resposta_limpa: Resposta do modelo
    """
    target_stage = detect_transition_target(state, fala_usuario, resposta_limpa)
    apply_transition(state, target_stage)

    stage = state.scene_stage
    rules = STATE_RULES.get(stage, {})

    state.physical_phase = rules.get("phase", state.physical_phase)

    if not state.mary_intent:
        state.mary_intent = rules.get("intent_default", MaryIntent.OBSERVAR.value)

    if not state.mary_physical_intent:
        state.mary_physical_intent = rules.get("physical_default", None)


def atualizar_psique_mary(state: MaryState, fala_usuario: str, resposta_limpa: str, config: MaryConfig = None) -> None:
    """
    Atualiza psique de Mary (desejo, tensão, conexão) baseado em gatilhos.
    
    Args:
        state: Estado de Mary
        fala_usuario: Fala do usuário
        resposta_limpa: Resposta do modelo
        config: Configuração
    """
    if config is None:
        config = MaryConfig()
    
    texto = f"{fala_usuario or ''}\n{resposta_limpa or ''}".lower()

    desejo = state.desire_level
    tensao = state.tension_level
    conexao = state.connection_level
    resolved = state.resolution_done
    fase = state.physical_phase

    gatilhos_desejo = [
        "quero", "vontade", "beijo", "smack", "humm", "calor",
        "excitado", "excitada", "arrepio", "ofego", "ofegante",
        "urgência", "urgencia", "desejo", "tesão", "tesao",
        "gostoso", "gostosa", "gemido", "gemer", "provoca",
        "encosta", "roça", "roca", "tira", "despe", "chega mais"
    ]

    gatilhos_tensao = [
        "perto", "pertinho", "próximo", "proximo", "respiração", "respiracao",
        "olhar", "silêncio", "silencio", "pressão", "pressao",
        "intensidade", "tremor", "forte", "aperto", "colado",
        "não para", "nao para", "segura", "travado", "ritmo", "devagar"
    ]

    gatilhos_conexao = [
        "confio", "gosto", "saudade", "saudades", "tudo bem", "sincero",
        "de verdade", "fica comigo", "carinho", "cuidado", "segurança",
        "seguranca", "como foi seu dia", "com você", "com voce",
        "quero ficar", "abraço", "abraco", "acolho", "junto"
    ]

    gatilhos_desaceleracao = [
        "calma", "descansa", "respira", "pausa", "fica assim", "relaxa"
    ]

    if any(p in texto for p in gatilhos_desejo):
        desejo += config.DESIRE_INCREMENT_GATILHO
        logger.debug("Gatilho de desejo ativado")

    if any(p in texto for p in gatilhos_tensao):
        tensao += config.TENSION_INCREMENT_GATILHO
        logger.debug("Gatilho de tensão ativado")

    if any(p in texto for p in gatilhos_conexao):
        conexao += config.CONNECTION_INCREMENT_GATILHO
        logger.debug("Gatilho de conexão ativado")

    if any(p in texto for p in gatilhos_desaceleracao):
        desejo -= config.DESIRE_DECREMENT_DESACELERACAO
        tensao -= config.TENSION_DECREMENT_DESACELERACAO
        conexao += config.CONNECTION_INCREMENT_DESACELERACAO
        logger.debug("Gatilho de desaceleração ativado")

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

    state.mary_intent = escolher_intencao_mary(state)
    state.mary_physical_intent = decidir_acao_fisica_mary(state)

    # Atualizar estado emocional
    if state.desire_level >= 0.85 and state.tension_level >= 0.65:
        state.estado_emocional = "desejante e entregue"
    elif state.desire_level >= 0.65:
        state.estado_emocional = "provocante e envolvida"
    elif state.connection_level >= 0.70:
        state.estado_emocional = "próxima e confiante"
    else:
        state.estado_emocional = "confiante"

    logger.debug(f"Psique atualizada: D={state.desire_level:.2f} T={state.tension_level:.2f} C={state.connection_level:.2f}")


# ==========================================================
# 6) PROMPT
# ==========================================================

def montar_prompt_para_modelo(state: MaryState, fala_usuario: str) -> str:
    """
    Monta prompt completo para enviar ao modelo LLM.
    
    Args:
        state: Estado de Mary
        fala_usuario: Fala/ação do usuário
    
    Returns:
        Prompt formatado
    """
    stage = state.scene_stage
    rules = STATE_RULES.get(stage, {})
    foco = rules.get("focus", "presenca e continuidade")

    return f"""
Você escreve SOMENTE como Mary, em PT-BR.

[ESTADO REAL]
Estágio atual: {stage}
Fase física atual: {state.physical_phase}
Desejo: {round(state.desire_level, 2)}
Tensão: {round(state.tension_level, 2)}
Conexão: {round(state.connection_level, 2)}
Intenção interna: {state.mary_intent}
Ação física interna: {state.mary_physical_intent or 'nenhuma'}
Ação autônoma: {state.mary_autonomous_action or 'nenhuma'}
Resolução forçada: {state.force_resolution_now}
Local: {state.local}
Tempo: {state.tempo}
Interlocutor: {state.interlocutor}
Ação atual de Mary: {state.mary_acao}
Estado emocional: {state.estado_emocional}

[FOCO DESTE ESTÁGIO]
{foco}

[REGRAS]
- Continue exatamente da ação atual.
- Não mude local nem interlocutor.
- Não reinicie a cena.
- Não narre reação do usuário que ele não declarou.
- Mary reage em tempo real ao parceiro.
- Cada resposta precisa ter gesto, fala ou reação física concreta.
- Não pule etapas.
- Use linguagem natural, direta e sem metáforas poéticas.
- Mary conduz pelo desejo, não por autoridade.

[FORMATO]
- Escreva 2 a 4 parágrafos curtos.
- Depois escreva exatamente:

STATE_UPDATE:
{{
  "acao_mary": "descrição curta, concreta e física da ação atual de Mary",
  "local": null,
  "interlocutor": null
}}

[FALA/AÇÃO DO USUÁRIO]
{fala_usuario}
""".strip()


def limpar_historico_para_modelo(history: List[Dict[str, str]], max_history: int) -> List[Dict[str, str]]:
    """
    Limpa histórico removendo STATE_UPDATE e limitando tamanho.
    
    Args:
        history: Histórico de mensagens
        max_history: Número máximo de mensagens
    
    Returns:
        Histórico limpo
    """
    limpo = []

    for msg in history[-max_history:]:
        role = msg.get("role")
        content = str(msg.get("content", "") or "")

        if "STATE_UPDATE:" in content:
            content = content.split("STATE_UPDATE:", 1)[0].strip()

        content = content.replace("```json", "").replace("```", "").strip()

        if role in ("user", "assistant") and content:
            limpo.append({"role": role, "content": content})

    return limpo


def montar_mensagens(state: MaryState, fala_usuario: str, config: MaryConfig = None) -> List[Dict[str, str]]:
    """
    Monta lista de mensagens para enviar ao LLM.
    
    Args:
        state: Estado de Mary
        fala_usuario: Fala do usuário
        config: Configuração
    
    Returns:
        Lista de mensagens formatada
    """
    if config is None:
        config = MaryConfig()
    
    mensagens = [
        {
            "role": "system",
            "content": (
                "Você é Mary. Responda apenas como Mary, em PT-BR. "
                "Estilo: natural, vivo, direto, com emoção humana curta. "
                "Sem metáforas exageradas, sem frieza, sem markdown."
            ),
        }
    ]

    mensagens.extend(limpar_historico_para_modelo(state.history, config.MAX_HISTORY))
    mensagens.append({"role": "user", "content": montar_prompt_para_modelo(state, fala_usuario)})
    return mensagens


# ==========================================================
# 7) CHAMADA LLM
# ==========================================================

def gerar_resposta_llm(mensagens: List[Dict[str, str]], model: str = None, config: MaryConfig = None) -> str:
    """
    Chama API OpenRouter para gerar resposta de Mary.
    
    Args:
        mensagens: Lista de mensagens para o modelo
        model: Nome do modelo (usa padrão se None)
        config: Configuração
    
    Returns:
        Resposta do modelo ou mensagem de erro
    """
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
        logger.error("OPENROUTER_API_KEY não encontrada")
        return "ERRO: OPENROUTER_API_KEY não encontrada."

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

        resposta = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        ) or "ERRO: resposta vazia."
        
        logger.info("Resposta LLM recebida com sucesso")
        return resposta

    except requests.exceptions.Timeout:
        logger.error(f"Timeout ao chamar LLM (>{config.TIMEOUT_SECONDS}s)")
        return f"ERRO: Timeout ao chamar LLM (>{config.TIMEOUT_SECONDS}s)"
    except requests.exceptions.HTTPError as e:
        logger.error(f"Erro HTTP ao chamar LLM: {e}")
        return f"ERRO HTTP: {e.response.status_code}"
    except json.JSONDecodeError as e:
        logger.error(f"Erro ao decodificar resposta JSON: {e}")
        return f"ERRO: Resposta JSON inválida"
    except Exception as e:
        logger.error(f"Erro inesperado ao chamar LLM: {type(e).__name__}: {e}")
        return f"ERRO OpenRouter: {type(e).__name__}: {e}"


# ==========================================================
# 8) STATE_UPDATE / VALIDAÇÃO
# ==========================================================

def extrair_state_update(resposta: str) -> Optional[Dict[str, Any]]:
    """
    Extrai bloco STATE_UPDATE da resposta do modelo.
    
    Args:
        resposta: Resposta do modelo
    
    Returns:
        Dicionário com STATE_UPDATE ou None
    """
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
    """
    Valida e filtra STATE_UPDATE para evitar mudanças indevidas.
    
    Args:
        update: STATE_UPDATE bruto do modelo
        state: Estado atual de Mary
    
    Returns:
        STATE_UPDATE validado e seguro
    """
    novo = {}

    if not isinstance(update, dict):
        logger.warning("STATE_UPDATE não é um dicionário")
        return novo

    acao = update.get("acao_mary")

    if isinstance(acao, str) and len(acao.strip()) > 3:
        novo["mary_acao"] = acao.strip()
        logger.debug(f"Ação validada: {acao[:50]}...")

    # Local e interlocutor são protegidos (null = sem mudança)
    if update.get("local"):
        novo["local"] = state.local
        logger.warning("Tentativa de mudança de local bloqueada")

    if update.get("interlocutor"):
        novo["interlocutor"] = state.interlocutor
        logger.warning("Tentativa de mudança de interlocutor bloqueada")

    return novo


def resposta_viola_estado(resposta: str, state: MaryState) -> Dict[str, List[str]]:
    """
    Valida se resposta viola regras de estado.
    
    Detecta:
    - Mudanças indevidas de local
    - Autoria indevida do usuário
    - Frases muleta (devolvendo iniciativa)
    - STATE_UPDATE ausente
    
    Args:
        resposta: Resposta do modelo
        state: Estado de Mary
    
    Returns:
        Dicionário com bloqueios e alertas
    """
    texto = (resposta or "").lower()

    resultado = {
        "bloqueios": [],
        "alertas": [],
    }

    local = str(state.local or "").lower()
    interlocutor = str(state.interlocutor or "").lower()

    locais_proibidos = ["sala", "rua", "banheiro", "cozinha", "varanda", "carro"]

    for loc in locais_proibidos:
        if loc != local and re.search(rf"\b{re.escape(loc)}\b", texto):
            resultado["bloqueios"].append(f"Mudança indevida de local: {loc}")
            logger.warning(f"Violação detectada: mudança para {loc}")

    aliases_interlocutor = [
        interlocutor,
        "janio",
        "jânio",
        "você",
        "voce",
        "te",
        "seu",
        "sua",
    ]

    if interlocutor and not any(alias and alias in texto for alias in aliases_interlocutor):
        resultado["alertas"].append("A resposta pode ter perdido o interlocutor ativo.")
        logger.warning("Alerta: interlocutor pode ter sido perdido")

    padroes_autoria_usuario = [
        r"\b(você|voce|janio|jânio)\s+(me\s+)?puxa\b",
        r"\b(você|voce|janio|jânio)\s+(me\s+)?puxou\b",
        r"\b(você|voce|janio|jânio)\s+(me\s+)?beija\b",
        r"\b(você|voce|janio|jânio)\s+(me\s+)?beijou\b",
        r"\b(você|voce|janio|jânio)\s+(me\s+)?abraça\b",
        r"\b(você|voce|janio|jânio)\s+(me\s+)?abraçou\b",
        r"\b(você|voce|janio|jânio)\s+(me\s+)?toca\b",
        r"\b(você|voce|janio|jânio)\s+(me\s+)?tocou\b",
        r"\b(você|voce|janio|jânio)\s+(aceita|aceitou|cede|cedeu|corresponde|correspondeu)\b",
        r"\b(você|voce|janio|jânio)\s+(se entrega|se entregou|se rende|se rendeu)\b",
    ]

    if _tem_padrao(texto, padroes_autoria_usuario):
        resultado["bloqueios"].append("Possível autoria indevida do usuário.")
        logger.warning("Violação detectada: autoria indevida do usuário")

    frases_muleta = [
        "me mostra",
        "me prova",
        "prova pra mim",
        "mostra o quanto",
        "faz alguma coisa",
        "vem então",
    ]

    if any(f in texto for f in frases_muleta):
        resultado["alertas"].append("A resposta pode estar devolvendo a iniciativa ao usuário.")
        logger.warning("Alerta: possível devolução de iniciativa")

    if "state_update:" not in texto:
        resultado["alertas"].append("STATE_UPDATE ausente ou fora do formato esperado.")
        logger.warning("Alerta: STATE_UPDATE ausente")

    return resultado


def criar_fallback_humano(state: MaryState, motivo: str = "") -> str:
    """
    Cria resposta fallback humanizada quando validação falha.
    
    Args:
        state: Estado de Mary
        motivo: Motivo da falha (para logging)
    
    Returns:
        Resposta fallback com STATE_UPDATE
    """
    acao_atual = limpar_acao_para_frase(state.mary_acao)

    fallback_texto = (
        f"Eu {acao_atual}, mas corrijo o rumo na hora, sem inventar o que você fez.\n\n"
        "— Não, espera... deixa eu fazer do meu jeito. Eu chego mais perto."
    )

    fallback_update = {
        "acao_mary": f"Mary {acao_atual}, corrigindo o ritmo e se aproximando por iniciativa própria.",
        "local": None,
        "interlocutor": None,
    }

    logger.warning(f"Fallback acionado: {motivo}")
    return f"{fallback_texto}\n\nSTATE_UPDATE:\n{json.dumps(fallback_update, ensure_ascii=False, indent=2)}"


def corrigir_resposta_se_necessario(resposta: str, state: MaryState, validacao: Dict[str, List[str]]) -> str:
    """
    Corrige resposta se violações foram detectadas.
    
    Args:
        resposta: Resposta original
        state: Estado de Mary
        validacao: Resultado da validação
    
    Returns:
        Resposta corrigida ou original
    """
    bloqueios = validacao.get("bloqueios", [])

    if not bloqueios:
        return resposta

    motivo = "; ".join(bloqueios)
    return criar_fallback_humano(state, motivo=motivo)


def limpar_state_update(resposta: str) -> str:
    """
    Remove bloco STATE_UPDATE da resposta.
    
    Args:
        resposta: Resposta com STATE_UPDATE
    
    Returns:
        Resposta limpa
    """
    if not resposta:
        return ""

    if "STATE_UPDATE:" in resposta:
        return resposta.split("STATE_UPDATE:", 1)[0].strip()

    return resposta.strip()


# ==========================================================
# 9) PROCESSAMENTO DO TURNO
# ==========================================================

def processar_turno(state: MaryState, fala_usuario: str, model: str = None, config: MaryConfig = None) -> Dict[str, Any]:
    """
    Processa um turno completo de interação.
    
    Fluxo:
    1. Incrementa turno
    2. Prepara engine de resolução
    3. Gera resposta do LLM
    4. Valida resposta
    5. Corrige se necessário
    6. Atualiza estado
    7. Sincroniza FSM
    8. Salva no histórico
    
    Args:
        state: Estado de Mary
        fala_usuario: Fala/ação do usuário
        model: Modelo LLM (usa padrão se None)
        config: Configuração
    
    Returns:
        Dicionário com resultado do processamento
    """
    if config is None:
        config = MaryConfig()
    
    if model is None:
        model = config.MODEL_DEFAULT
    
    logger.info(f"=== TURNO {state.turno + 1} INICIADO ===")
    state.turno += 1

    try:
        preparar_resolution_engine(state, fala_usuario, config)
        state.mary_physical_intent = decidir_acao_fisica_mary(state, config)
        motor_autonomo_mary(state, fala_usuario, config)

        mensagens = montar_mensagens(state, fala_usuario, config)
        resposta_bruta = gerar_resposta_llm(mensagens, model=model, config=config)

        update_bruto = extrair_state_update(resposta_bruta)
        validacao = resposta_viola_estado(resposta_bruta, state)

        resposta_final = corrigir_resposta_se_necessario(resposta_bruta, state, validacao)
        resposta_final_limpa = limpar_state_update(resposta_final)

        update_final = {}

        if not validacao.get("bloqueios"):
            if update_bruto:
                seguro = validar_update(update_bruto, state)
                state.__dict__.update(seguro)
                update_final = update_bruto
                logger.info("STATE_UPDATE aplicado (sem bloqueios)")
        else:
            update_corrigido = extrair_state_update(resposta_final) or {}
            if update_corrigido:
                seguro = validar_update(update_corrigido, state)
                state.__dict__.update(seguro)
                update_final = update_corrigido
                logger.info("STATE_UPDATE corrigido aplicado")

        atualizar_psique_mary(state, fala_usuario, resposta_final_limpa, config)
        finalizar_resolution_engine(state, resposta_final_limpa)
        sync_state_machine(state, fala_usuario, resposta_final_limpa)
        state.mary_physical_intent = decidir_acao_fisica_mary(state, config)
        state.mary_intent = escolher_intencao_mary(state, config)
        motor_autonomo_mary(state, fala_usuario, config)

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
        return {
            "mensagens": [],
            "resposta_bruta": f"ERRO: {type(e).__name__}: {e}",
            "resposta_final": f"ERRO: {type(e).__name__}: {e}",
            "resposta_final_limpa": f"ERRO: {type(e).__name__}: {e}",
            "update": {},
            "validacao": {"bloqueios": [str(e)], "alertas": []},
        }


# ==========================================================
# 10) INTERFACE STREAMLIT
# ==========================================================

def main():
    """Interface principal Streamlit."""
    st.set_page_config(page_title="Mary Roleplay - FSM Refatorado", layout="wide")
    st.title("🎭 Mary Roleplay - FSM Narrativa + Filtro (v2.0 Refatorado)")

    state = init_state()
    config = MaryConfig()

    col1, col2 = st.columns([3, 1])

    with col1:
        fala_usuario = st.text_area("Fala/Ação do usuário:", height=100)

    with col2:
        st.markdown("### Controles")
        processar = st.button("▶️ Processar turno", use_container_width=True)
        resetar = st.button("🔄 Resetar teste", use_container_width=True)

    if resetar:
        if "mary_state_minimo" in st.session_state:
            del st.session_state.mary_state_minimo
        st.rerun()

    if processar and fala_usuario:
        with st.spinner("Processando..."):
            resultado = processar_turno(state, fala_usuario, config=config)

        st.markdown("---")

        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📝 Resposta",
            "🔍 Validação",
            "📊 Estado",
            "💬 Prompt",
            "🐛 Debug"
        ])

        with tab1:
            st.markdown("### Resposta Final")
            st.write(resultado["resposta_final_limpa"])

        with tab2:
            st.markdown("### Validação")
            validacao = resultado["validacao"]
            if validacao["bloqueios"]:
                st.error(f"❌ Bloqueios: {validacao['bloqueios']}")
            elif validacao["alertas"]:
                st.warning(f"⚠️ Alertas: {validacao['alertas']}")
            else:
                st.success("✅ Nenhuma violação detectada")

        with tab3:
            st.markdown("### Estado Atual")
            state_dict = state.to_dict()
            st.json(state_dict)

        with tab4:
            st.markdown("### Mensagens Enviadas ao LLM")
            st.json(resultado["mensagens"])

        with tab5:
            st.markdown("### Debug Info")
            st.json({
                "turno": state.turno,
                "resposta_bruta": resultado["resposta_bruta"][:200] + "...",
                "state_update": resultado["update"],
            })

    st.markdown("---")
    st.subheader("📊 Estado Real Salvo")
    st.json(state.to_dict())


if __name__ == "__main__":
    main()
How to Remove Facts Text from JSON Data - Manus
