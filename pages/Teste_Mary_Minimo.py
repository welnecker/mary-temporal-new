import re
import json
import logging
import streamlit as st
import requests
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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
    shared_resolution_done: bool = False
    force_resolution_now: bool = False
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
            "resolution_done": self.resolution_done,
            "shared_resolution_done": self.shared_resolution_done,
            "mary_physical_intent": self.mary_physical_intent,
            "force_resolution_now": self.force_resolution_now,
            "mary_autonomous_action": self.mary_autonomous_action,
            "style_profile": self.style_profile,
        }


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
        "ao meu lado", "senta", "sentou", "inclino", "olha pra mim"
    ],
    "toque": [
        "toque", "toco", "encosto", "encosta", "mao",
        "braco", "ombro", "nuca", "seguro", "acaricia",
        "desliza a mao", "cintura", "roca"
    ],
    "beijo": [
        "beijo", "beija", "beijou", "smack", "labios",
        "boca", "morde de leve", "beijo no pescoco"
    ],
    "intensidade": [
        "intenso", "corpo contra", "pressiono", "nao para",
        "colado", "forte", "aperto", "encaixo", "ritmo", "guia", "provoca"
    ],
    "pico": [
        "auge", "climax", "perco o controle", "me solto",
        "gozo", "gozando", "vindo", "vou gozar", "gozei"
    ],
    "desaceleracao": [
        "respiracao", "respiro", "devagar", "tremor",
        "silencio", "pausa", "ofego", "desacelero",
        "relaxo", "corpo mole"
    ],
    "aftercare": [
        "fica comigo", "vem aqui", "abraco", "carinho",
        "descanso", "aftercare", "acolho", "fica assim", "deita aqui"
    ],
}


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


def init_state() -> MaryState:
    if "mary_state_minimo" not in st.session_state:
        st.session_state.mary_state_minimo = MaryState()
        logger.info("Estado inicial de Mary criado")
    return st.session_state.mary_state_minimo


def reparar_estado_incoerente(state: MaryState) -> None:
    fase = state.physical_phase
    resolved = state.resolution_done
    if not resolved and fase >= 6:
        logger.warning("Estado incoerente detectado: fase >= 6 sem resolucao. Corrigindo...")
        state.physical_phase = 5
        state.scene_stage = "pico"

def detectar_reacendimento_pos_aftercare(state: MaryState, fala_usuario: str) -> bool:
    """
    Detecta quando a cena já passou por resolução/aftercare,
    mas o usuário reacende o clima.

    Não apaga memória.
    Apenas inicia um novo ciclo físico.
    """
    texto = (fala_usuario or "").lower()

    if state.scene_stage not in {"aftercare", "desaceleracao"}:
        return False

    if not state.resolution_done:
        return False

    gatilhos_reacendimento = [
        "tesão voltou",
        "tesao voltou",
        "fogo voltando",
        "de novo",
        "mais uma vez",
        "quero de novo",
        "não acabou",
        "nao acabou",
        "continua",
        "vem cá",
        "vem ca",
        "me beija",
        "smack",
        "humm",
        "tô ficando",
        "to ficando",
        "tá vendo",
        "ta vendo",
        "me arrepia",
        "adoro quando",
    ]

    return any(g in texto for g in gatilhos_reacendimento)


def preparar_resolution_engine(state: MaryState, fala_usuario: str = "", config: MaryConfig = None) -> None:
    if config is None:
        config = MaryConfig()

    reparar_estado_incoerente(state)

    texto_user = (fala_usuario or "").lower()

    desejo = state.desire_level
    tensao = state.tension_level
    conexao = state.connection_level
    fase = state.physical_phase
    resolved = state.resolution_done

    # ==========================================================
    # 1) USUÁRIO ANUNCIA O PRÓPRIO PICO
    # Impede que o motor pule direto para desaceleração/aftercare.
    # ==========================================================
    usuario_anuncia_pico = any(p in texto_user for p in [
        "vou gozar",
        "vou chegar",
        "estou gozando",
        "tô gozando",
        "to gozando",
        "vou explodir",
        "vem junto",
    ])

    if usuario_anuncia_pico and state.scene_stage in {"pico", "desaceleracao", "intensidade"}:
        logger.info("Usuario anunciou pico; mantendo cena em pico compartilhado")

        state.force_resolution_now = True
        state.physical_phase = 5
        state.scene_stage = "pico"
        state.mary_intent = "resolver_pico"
        state.mary_physical_intent = "resolver_pico"
        return

    # ==========================================================
    # 2) ESTADO INTERNO PEDE AVANÇO
    # Mary não deve ficar presa em intensidade quando os níveis
    # já estão altos e o usuário está receptivo.
    # ==========================================================
    estado_pede_avanco = (
        not resolved
        and fase >= 4
        and desejo >= 0.90
        and tensao >= 0.70
        and conexao >= 0.55
    )

    usuario_receptivo = any(p in texto_user for p in [
        "delicia",
        "delícia",
        "humm",
        "ahh",
        "ahhh",
        "smack",
        "chup",
        "continua",
        "assim",
        "gostoso",
        "gostosa",
        "tesao",
        "tesão",
    ])

    if estado_pede_avanco and usuario_receptivo:
        logger.info("Estado interno pede avanço; elevando para pico")

        state.force_resolution_now = True
        state.physical_phase = 5
        state.scene_stage = "pico"
        state.mary_intent = "resolver_pico"
        state.mary_physical_intent = "resolver_pico"
        return

    # ==========================================================
    # 3) GATILHOS EXPLÍCITOS DE RESOLUÇÃO
    # Mantém compatibilidade com sua lógica anterior.
    # ==========================================================
    gatilhos_resolucao_do_usuario = [
        "agora resolve",
        "chega ao auge",
        "pode finalizar",
        "finaliza",
        "vai ate o fim",
        "vai até o fim",
        "termina",
        "nao segura",
        "não segura",
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

    # ==========================================================
    # 4) FALLBACK NORMAL
    # Não deixa a função quebrar nem depender de variável ausente.
    # ==========================================================
    state.force_resolution_now = False
    state.scene_stage = fase_para_stage(state.physical_phase)

    if not resolved and fase >= 4:
        state.mary_intent = "resolver_pico"
        state.mary_physical_intent = decidir_acao_fisica_mary(state, config)


def finalizar_resolution_engine(state: MaryState, resposta_limpa: str) -> None:
    """
    Finaliza a resolução sem cortar o pico compartilhado cedo demais.

    Ideia:
    - Se force_resolution_now veio de um anúncio de pico do usuário,
      mantém a cena em PICO por mais um turno.
    - Só depois permite ir para desaceleração.
    """

    if state.force_resolution_now:
        logger.info("Finalizando resolucao forcada / compartilhada")

        # ==========================================================
        # 1) PRIMEIRA PASSAGEM: segura a cena no pico
        # ==========================================================
        if not getattr(state, "shared_resolution_done", False):
            setattr(state, "shared_resolution_done", True)

            state.resolution_done = False
            state.physical_phase = 5
            state.scene_stage = "pico"
            state.mary_intent = "resolver_pico"
            state.mary_physical_intent = "resolver_pico"
            state.force_resolution_now = False

            logger.info("Resolucao compartilhada mantida em pico por mais um turno")
            return

        # ==========================================================
        # 2) SEGUNDA PASSAGEM: agora sim desacelera
        # ==========================================================
        state.resolution_done = True
        state.physical_phase = 6
        state.scene_stage = "desaceleracao"
        state.mary_intent = "desacelerar"
        state.mary_physical_intent = "desacelerar_com_contato"
        state.force_resolution_now = False

        logger.info("Resolucao concluida; indo para desaceleracao")
        return

    state.force_resolution_now = False


def decidir_acao_fisica_mary(state: MaryState, config: MaryConfig = None) -> Optional[str]:
    if config is None:
        config = MaryConfig()
    
    desejo = state.desire_level
    tensao = state.tension_level
    conexao = state.connection_level
    fase = state.physical_phase
    resolved = state.resolution_done

    if resolved:
        if conexao >= config.CONNECTION_THRESHOLD_PROXIMIDADE:
            return "manter_proximidade"
        return "desacelerar_com_contato"

    if fase <= 0 and desejo >= config.DESIRE_THRESHOLD_APROXIMACAO:
        return "aproximar_devagar"

    if fase == 1:
        if desejo >= config.DESIRE_THRESHOLD_TOQUE:
            return "reduzir_distancia"
        return "presenca_provocante"

    if fase == 2:
        if desejo >= config.DESIRE_THRESHOLD_TOQUE_PROFUNDO:
            return "explorar_toque"
        return "toque_leve"

    if fase == 3:
        if desejo >= config.DESIRE_THRESHOLD_BEIJO_PROFUNDO:
            return "aprofundar_beijo"
        return "manter_beijo"

    if fase == 4:
        if desejo >= config.DESIRE_THRESHOLD_INTENSIDADE and tensao >= config.TENSION_THRESHOLD_INTENSIDADE:
            return "intensificar_contato"
        return "sustentar_ritmo"

    if fase >= 5:
        if desejo >= config.DESIRE_THRESHOLD_PICO:
            return "resolver_pico"
        return "manter_intensidade"

    return None


def escolher_intencao_mary(state: MaryState, config: MaryConfig = None) -> str:
    if config is None:
        config = MaryConfig()
    
    desejo = state.desire_level
    tensao = state.tension_level
    conexao = state.connection_level
    fase = state.physical_phase
    resolved = state.resolution_done

    if resolved:
        if conexao >= config.CONNECTION_THRESHOLD_AFTERCARE:
            return "aftercare_presente"
        if desejo >= config.DESIRE_THRESHOLD_BEIJO:
            return "manter_proximidade"
        return "desacelerar"

    if fase <= 0:
        if desejo >= config.DESIRE_THRESHOLD_TOQUE:
            return "puxar_proximidade"
        return "observar"

    if fase == 1:
        if tensao >= config.TENSION_THRESHOLD_APROXIMACAO:
            return "convidar_aproximacao"
        return "aquecer_clima"

    if fase == 2:
        if desejo >= config.DESIRE_THRESHOLD_TOQUE_PROFUNDO:
            return "aprofundar_toque"
        return "testar_receptividade"

    if fase == 3:
        if desejo >= config.DESIRE_THRESHOLD_BEIJO:
            return "aprofundar_contato"
        return "sustentar_beijo"

    if fase == 4:
        if desejo >= config.DESIRE_THRESHOLD_INTENSIDADE:
            return "buscar_intensidade"
        return "manter_ritmo"

    if fase >= 5:
        return "resolver_pico"

    return "observar"


def motor_variacoes_mary_generico(state: MaryState, fala_usuario: str, history: List[Dict[str, str]]) -> Optional[str]:
    """
    Motor generico de variacoes que escala com o nivel de intimidade.
    Funciona para qualquer contexto: camisa, calca, etc.
    """
    texto = (fala_usuario or "").lower()
    desejo = state.desire_level
    fase = state.physical_phase
    
    # Detecta nivel de desvestimento
    tem_camisa_fora = any(p in texto for p in ["tirar camisa", "camisa fora", "sem camisa", "pele", "peito", "seios", "mamilo", "abdomem", "torso"])
    tem_calca_fora = any(p in texto for p in ["tirar calca", "calca fora", "sem calca", "calcinha", "slip", "cueca", "nua", "nu", "intimo"])
    
    # Conta repeticoes no historico recente
    historico_recente = history[-8:] if len(history) > 8 else history
    texto_historico = " ".join([msg.get("content", "").lower() for msg in historico_recente])
    
    beijos = texto_historico.count("beijo") + texto_historico.count("beija")
    mordidas = texto_historico.count("muerdo") + texto_historico.count("mordo")
    lambidas = texto_historico.count("lambo") + texto_historico.count("lingua")
    acaricia = texto_historico.count("acaricia") + texto_historico.count("desliza")
    
    repeticoes = beijos + mordidas + lambidas + acaricia
    
    # NIVEL 1: Sem camisa (fase 3-4, desejo 0.60+)
    if tem_camisa_fora and not tem_calca_fora and desejo >= 0.60 and repeticoes >= 3:
        variacoes_nivel1 = [
            "Eu muerdo seu pescoço com força, deixando marcas que você vai sentir depois.",
            "Eu deslizo minha boca para o seu mamilo e muerdo de leve.",
            "Eu passo minha lingua pelo seu abdômen, deixando um rastro de beijos.",
            "Eu muerdo seu ombro enquanto minha mão desce pela sua cintura.",
            "Eu lambo seu pescoço lentamente, depois muerdo com mais força.",
            "Eu beijo seu peito, depois seu abdômen, descendo devagar.",
            "Minha boca explora seu torso enquanto minha mão aperta sua cintura.",
            "Eu muerdo a linha do seu queixo e depois desço para seu pescoço.",
        ]
        return variacoes_nivel1[repeticoes % len(variacoes_nivel1)]
    
    # NIVEL 2: Sem calca (fase 4-5, desejo 0.80+)
    elif tem_calca_fora and desejo >= 0.80 and repeticoes >= 4:
        variacoes_nivel2 = [
            "Eu deslizo minha boca para baixo, deixando beijos na sua barriga e depois mais perto.",
            "Eu muerdo a parte interna da sua coxa, deixando marcas que você vai lembrar depois.",
            "Minha lingua percorre seu corpo enquanto minha mão aperta sua cintura.",
            "Eu sussurro contra sua pele: 'Voce e meu agora' e continuo descendo.",
            "Eu beijo a linha do seu abdômen, descendo devagar enquanto sinto você reagir.",
            "Minha boca encontra a sua novamente, mas dessa vez meu corpo esta completamente colado no seu.",
            "Eu muerdo seu lábio inferior e puxo levemente enquanto minha mão desce.",
            "Eu sussurro 'Eu quero voce agora' e deslizo minha boca pelo seu corpo.",
        ]
        return variacoes_nivel2[repeticoes % len(variacoes_nivel2)]
    
    # NIVEL 3: Ambos nus (fase 5+, desejo 0.90+)
    elif tem_camisa_fora and tem_calca_fora and desejo >= 0.90 and repeticoes >= 5:
        variacoes_nivel3 = [
            "Eu me posiciono sobre voce e sussurro: 'Agora e sua vez de me tocar'.",
            "Meu corpo se move contra o seu enquanto eu sussurro seu nome no seu ouvido.",
            "Eu guio sua mao para onde eu quero que voce me toque.",
            "Eu me entrego completamente a voce, deixando meu corpo falar tudo que minha boca nao consegue.",
            "Eu sussurro: 'Voce esta me deixando louca' enquanto meu corpo se move.",
            "Eu aperto voce contra mim e sussurro: 'Nao para, por favor'.",
        ]
        return variacoes_nivel3[repeticoes % len(variacoes_nivel3)]
    
    return None





def motor_autonomo_mary(state: MaryState, fala_usuario: str = "", config: MaryConfig = None) -> None:
    if config is None:
        config = MaryConfig()
    
    fase = state.physical_phase
    desejo = state.desire_level
    tensao = state.tension_level
    conexao = state.connection_level
    resolved = state.resolution_done
    texto_user = (fala_usuario or "").lower()

    pediu_aproximacao = any(p in texto_user for p in [
        "vem mais", "chega mais", "encosta", "perto", "pertinho",
        "vem aqui", "fica perto", "aproxima",
    ])

    perguntou_emocao = any(p in texto_user for p in [
        "tudo bem", "estranha", "ta bem",
        "falando pouco", "o que foi", "voce ta",
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
            "Eu descelero com proximidade, cuidado e fala baixa. Nao fico fria e nao reinicio a intensidade."
        )
        logger.debug("Acao autonoma: desaceleracao pos-resolucao")
        return

    if perguntou_emocao:
        state.mary_autonomous_action = (
            "Eu respondo com emocao viva, admito o que estou sentindo sem drama, sorrio ou toco Janio de leve, "
            "e mostro que nao estou distante nem automatica."
        )
        logger.debug("Acao autonoma: resposta emocional")
        return

    if pediu_aproximacao:
        state.mary_autonomous_action = (
            "Eu atendo ao pedido com acao propria: aproximo o corpo, encosto de leve, uso fala curta e nao devolvo "
            "a iniciativa com frases vazias."
        )
        logger.debug("Acao autonoma: atender aproximacao")
        return

    if not resolved and fase >= 4 and desejo >= config.DESIRE_THRESHOLD_INTENSIDADE and tensao >= config.TENSION_THRESHOLD_INTENSIDADE:
        state.mary_autonomous_action = (
            "Eu ago com decisao, misturo gesto fisico, fala curta e reacao emocional clara. "
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
            "Eu crio vinculo com naturalidade: sorrio, reajo ao que Janio disse, me aproximo um pouco e falo com presenca."
        )
        logger.debug("Acao autonoma: criar vinculo")
        return

    state.mary_autonomous_action = (
        "Eu mantenho presenca ativa, com gesto simples, fala viva, leve provocacao e reacao emocional."
    )
    logger.debug("Acao autonoma: presenca ativa (padrao)")


def detect_transition_target(state: MaryState, fala_usuario: str, resposta_limpa: str) -> str:
    texto = f"{fala_usuario or ''}\n{resposta_limpa or ''}".lower()
    current_stage = state.scene_stage
    resolved = state.resolution_done

    if not resolved:
        for stage in ["pico", "intensidade", "beijo", "toque", "aproximacao"]:
            if any(p in texto for p in TRIGGER_MAP.get(stage, [])):
                logger.debug(f"Trigger detectado para estagio: {stage}")
                return stage
        return current_stage

    for stage in ["aftercare", "desaceleracao", "intensidade"]:
        if any(p in texto for p in TRIGGER_MAP.get(stage, [])):
            logger.debug(f"Trigger pos-resolucao detectado para estagio: {stage}")
            return stage

    return current_stage


def can_transition(current_stage: str, target_stage: str) -> bool:
    allowed = target_stage in TRANSITIONS.get(current_stage, set())
    if not allowed:
        logger.debug(f"Transicao bloqueada: {current_stage} -> {target_stage}")
    return allowed


def clamp_stage_step(current_stage: str, target_stage: str) -> str:
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
    current_stage = state.scene_stage
    resolved = state.resolution_done

    if target_stage in {"desaceleracao", "aftercare"} and not resolved:
        logger.debug(f"Bloqueando transicao para {target_stage} (nao resolvido)")
        target_stage = "pico"

    target_stage = clamp_stage_step(current_stage, target_stage)

    if not can_transition(current_stage, target_stage):
        logger.debug(f"Transicao invalida, mantendo estagio: {current_stage}")
        target_stage = current_stage

    state.scene_stage = target_stage
    state.physical_phase = stage_para_fase(target_stage)

    rules = STATE_RULES.get(target_stage, {})
    state.mary_intent = escolher_intencao_mary(state) or rules.get("intent_default", "observar")
    state.mary_physical_intent = decidir_acao_fisica_mary(state) or rules.get("physical_default", None)

    logger.info(f"Transicao aplicada: {current_stage} -> {target_stage}")


def sync_state_machine(state: MaryState, fala_usuario: str, resposta_limpa: str) -> None:
    target_stage = detect_transition_target(state, fala_usuario, resposta_limpa)
    apply_transition(state, target_stage)

    stage = state.scene_stage
    rules = STATE_RULES.get(stage, {})

    state.physical_phase = rules.get("phase", state.physical_phase)

    if not state.mary_intent:
        state.mary_intent = rules.get("intent_default", "observar")

    if not state.mary_physical_intent:
        state.mary_physical_intent = rules.get("physical_default", None)


def atualizar_psique_mary(state: MaryState, fala_usuario: str, resposta_limpa: str, config: MaryConfig = None) -> None:
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
        "urgencia", "desejo", "tesao",
        "gostoso", "gostosa", "gemido", "gemer", "provoca",
        "encosta", "roca", "tira", "despe", "chega mais"
    ]

    gatilhos_tensao = [
        "perto", "pertinho", "proximo", "respiracao",
        "olhar", "silencio", "pressao",
        "intensidade", "tremor", "forte", "aperto", "colado",
        "nao para", "segura", "travado", "ritmo", "devagar"
    ]

    gatilhos_conexao = [
        "confio", "gosto", "saudade", "saudades", "tudo bem", "sincero",
        "de verdade", "fica comigo", "carinho", "cuidado", "seguranca",
        "como foi seu dia", "com voce",
        "quero ficar", "abraco", "acolho", "junto"
    ]

    gatilhos_desaceleracao = [
        "calma", "descansa", "respira", "pausa", "fica assim", "relaxa"
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

    state.mary_intent = escolher_intencao_mary(state)
    state.mary_physical_intent = decidir_acao_fisica_mary(state)

    if state.desire_level >= 0.85 and state.tension_level >= 0.65:
        state.estado_emocional = "desejante e entregue"
    elif state.desire_level >= 0.65:
        state.estado_emocional = "provocante e envolvida"
    elif state.connection_level >= 0.70:
        state.estado_emocional = "proxima e confiante"
    else:
        state.estado_emocional = "confiante"

    logger.debug(f"Psique atualizada: D={state.desire_level:.2f} T={state.tension_level:.2f} C={state.connection_level:.2f}")


def montar_prompt_para_modelo(state: MaryState, fala_usuario: str) -> str:
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
Local: {state.local}
Tempo: {state.tempo}
Interlocutor: {state.interlocutor}
Acao atual de Mary: {state.mary_acao}
Estado emocional: {state.estado_emocional}

[FOCO DESTE ESTAGIO]
{foco}

[ESTILO DE MARY - EQUILIBRIO]
- Fala DIRETA e HONESTA (40-50% do texto).
- Narração de ACAO e MOVIMENTO (40-50% do texto).
- Mostra vulnerabilidade sem repetir fórmula fixa.
- Evite encadear "Eu quero", "Eu sinto", "Eu preciso" no mesmo turno.
- A emoção deve aparecer misturada à ação, não como slogan.
- Nao narra emocoes do usuario. Narra ACOES de Mary.
- Mary é ativa e conduz pelo próprio desejo, sem tomar ações do usuário como se fossem dele.
- Conduzir não significa dominar; significa escolher a próxima ação dela.

[ESTRUTURA OBRIGATORIA]
1. FALA DIRETA (40-50% do texto deve ser dialogo entre aspas)
2. NARACAO DE ACAO (40-50% do texto deve descrever movimento/gesto)
3. Termine com uma ACAO CONCRETA, nao com fala

[VARIEDADE REAL DE INICIO]
- Não use sempre o mesmo sujeito no início da fala.
- Alterne entre fala curta, reação física, constatação emocional e ação.
- Evite começar falas consecutivas com "Você", "Eu", "Meu corpo" ou "Não aguento".
- Não copie literalmente os exemplos deste prompt.
- Se a resposta anterior começou com "Você...", comece esta por ação ou reação sensorial de Mary.

FORMAS POSSÍVEIS:
- reação curta: "Assim..."
- confissão simples: "Eu queria negar, mas não consigo."
- ação primeiro: Eu aproximo minha boca do seu pescoço antes de falar.
- sensação concreta: O calor da sua pele muda meu ritmo.
- frase incompleta e humana: "Espera... fica assim."

[PROGRESSAO AUTONOMA]
- Mary não depende de uma nova ordem do usuário quando o estado já mostra desejo, tensão e conexão altos.
- Se o usuário reage positivamente, geme, beija, ri, elogia ou continua o contato, isso conta como consentimento narrativo para Mary continuar a própria ação.
- Mary deve transformar intensidade acumulada em consequência física concreta.
- Não repetir o mesmo ciclo: beijo → puxar → colar → dizer que quer → beijo.
- A cada turno, Mary deve fazer UMA mudança real de estado: posição, ritmo, peça de roupa, distância, foco do toque ou consequência emocional.
- Se a fase atual for intensidade, não voltar para aproximação ou toque leve.
- Se a fase atual for intensidade e os níveis estiverem altos, Mary avança sem pedir confirmação.
- Nao termine com: "quero ver", "deixo voce decidir", "vejo se", "fico esperando"
- Nao use palavras narrativas demais: "sentindo", "deixando", "deixo", "deixa"
- Nao ordene: "para de", "foca", "nao faca"
- Fale o que Mary QUER e SENTE. Seja vulneravel.
- Continue exatamente da acao atual.
- Nao mude local nem interlocutor.
- Nao reinicie a cena.
- Mary reage em tempo real ao parceiro.
- Use linguagem natural, direta e sem metaforas poeticas.
- Mary conduz pelo desejo, nao por autoridade.

[RESOLUCAO COMPARTILHADA]
- Se o usuário anuncia o próprio ápice, Mary NÃO deve pular direto para aftercare.
- Primeiro descreva a culminação emocional e física da cena de forma intensa, mas sem encerrar rápido demais.
- Mary deve manter a ação por alguns instantes, reagir ao que acontece e só depois desacelerar.
- Não transformar o ápice em uma frase curta seguida de descanso.
- A resposta deve ter: impacto imediato, reação de Mary, continuidade por alguns segundos e só então queda de ritmo.
- Não reiniciar a cena.
- Não pedir confirmação.
- Não devolver a iniciativa ao usuário.

[NOVO CICLO APOS AFTERCARE]
- Se a cena já teve aftercare, mas o usuário reacende o clima, Mary não deve agir como se fosse a primeira aproximação.
- Mary lembra do que acabou de acontecer.
- O novo ciclo começa com intimidade acumulada, não com timidez inicial.
- Mary pode reagir com surpresa, provocação leve ou carinho antes de voltar ao contato.
- Não repetir a mesma coreografia do ciclo anterior.
- Não ficar presa em abraço, pescoço e quadril colado se o clima está reacendendo.
- A progressão deve parecer natural: aftercare quente → novo toque → beijo/intensidade, conforme a reação do usuário.

[EXEMPLOS BOM - EQUILIBRIO]
BOM: "Voce me deixa louca. Eu quero mais de voce." + Eu puxo voce para perto.
BOM: "Meu corpo ja esta dizendo o que eu quero." + Minha mao desliza para sua cintura.
BOM: "Nao aguento mais esperar." + Eu beijo seu pescoco com intensidade.
BOM: "Isso. Exatamente assim." + Meu corpo se move contra o seu.

[EXEMPLOS RUIM]
RUIM: Muito fala, pouca acao: "Eu quero, eu sinto, eu preciso..." (3 paragrafos)
RUIM: Muito naracao, pouca fala: "Eu deslizo, eu passo, eu beijo..." (sem dialogo)
RUIM: Muita repeticao: "Eu quero... Eu preciso... Eu estou..."

[FORMATO]
- Escreva 2 a 3 paragrafos CURTOS.
- Cada paragrafo: 1-2 frases de FALA + 1-2 frases de ACAO.
- Termine com uma ACAO CONCRETA (nao com fala).
- Depois escreva exatamente:

STATE_UPDATE:
{{
  "acao_mary": "descricao curta, concreta e fisica da acao atual de Mary",
  "local": null,
  "interlocutor": null
}}

[FALA/ACAO DO USUARIO]
{fala_usuario}""".strip()


def limpar_historico_para_modelo(history: List[Dict[str, str]], max_history: int) -> List[Dict[str, str]]:
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
    if config is None:
        config = MaryConfig()
    
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


def gerar_resposta_llm(mensagens: List[Dict[str, str]], model: str = None, config: MaryConfig = None) -> str:
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
        return "ERRO: Resposta JSON invalida"
    except Exception as e:
        logger.error(f"Erro inesperado ao chamar LLM: {type(e).__name__}: {e}")
        return f"ERRO OpenRouter: {type(e).__name__}: {e}"


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
    novo = {}
    if not isinstance(update, dict):
        logger.warning("STATE_UPDATE nao e um dicionario")
        return novo
    acao = update.get("acao_mary")
    if isinstance(acao, str) and len(acao.strip()) > 3:
        novo["mary_acao"] = acao.strip()
        logger.debug(f"Acao validada: {acao[:50]}...")
    if update.get("local"):
        novo["local"] = state.local
        logger.warning("Tentativa de mudanca de local bloqueada")
    if update.get("interlocutor"):
        novo["interlocutor"] = state.interlocutor
        logger.warning("Tentativa de mudanca de interlocutor bloqueada")
    return novo


def resposta_viola_estado(resposta: str, state: MaryState) -> Dict[str, List[str]]:
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
            resultado["bloqueios"].append(f"Mudanca indevida de local: {loc}")
            logger.warning(f"Violacao detectada: mudanca para {loc}")
    aliases_interlocutor = [
        interlocutor,
        "janio",
        "voce",
        "te",
        "seu",
        "sua",
    ]
    if interlocutor and not any(alias and alias in texto for alias in aliases_interlocutor):
        resultado["alertas"].append("A resposta pode ter perdido o interlocutor ativo.")
        logger.warning("Alerta: interlocutor pode ter sido perdido")
    padroes_autoria_usuario = [
        r"\b(voce|janio)\s+(me\s+)?puxa\b",
        r"\b(voce|janio)\s+(me\s+)?puxou\b",
        r"\b(voce|janio)\s+(me\s+)?beija\b",
        r"\b(voce|janio)\s+(me\s+)?beijou\b",
        r"\b(voce|janio)\s+(me\s+)?abraca\b",
        r"\b(voce|janio)\s+(me\s+)?abracou\b",
        r"\b(voce|janio)\s+(me\s+)?toca\b",
        r"\b(voce|janio)\s+(me\s+)?tocou\b",
        r"\b(voce|janio)\s+(aceita|aceitou|cede|cedeu|corresponde|correspondeu)\b",
        r"\b(voce|janio)\s+(se entrega|se entregou|se rende|se rendeu)\b",
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
    ]
    if any(f in texto for f in frases_muleta):
        resultado["alertas"].append("A resposta pode estar devolvendo a iniciativa ao usuario.")
        logger.warning("Alerta: possivel devolucao de iniciativa")
    if "state_update:" not in texto:
        resultado["alertas"].append("STATE_UPDATE ausente ou fora do formato esperado.")
        logger.warning("Alerta: STATE_UPDATE ausente")
    return resultado


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
    return f"{fallback_texto}\n\nSTATE_UPDATE:\n{json.dumps(fallback_update, ensure_ascii=False, indent=2)}"


def corrigir_resposta_se_necessario(resposta: str, state: MaryState, validacao: Dict[str, List[str]]) -> str:
    # FALLBACK REMOVIDO PARA DIAGNOSTICO
    # Deixar o LLM errar sem disfarce para ver o padrao real
    return resposta


def limpar_state_update(resposta: str) -> str:
    if not resposta:
        return ""
    if "STATE_UPDATE:" in resposta:
        return resposta.split("STATE_UPDATE:", 1)[0].strip()
    return resposta.strip()

def detectar_consequencia_da_resposta(state: MaryState, resposta_limpa: str) -> bool:
    """
    Lê a resposta final da Mary e consolida o estado real.
    Retorna True quando encontrou uma consequência forte que deve travar o estado.
    """
    texto = (resposta_limpa or "").lower()

    sinais_pico_mary = [
        "começo a gozar",
        "comecei a gozar",
        "estou gozando",
        "gozo",
        "gozei",
        "espasmos",
        "meu corpo inteiro entra em colapso",
        "meu corpo inteiro entrar em colapso",
        "desabo",
        "desabei",
        "corpo continua tremendo",
        "ondas lentas",
        "perco totalmente o controle",
        "perdi totalmente o controle",
        "travo contra o seu",
        "travo o corpo",
        "meu corpo trava",
    ]

    if any(s in texto for s in sinais_pico_mary):
        logger.info("Detector pos-resposta: pico de Mary consolidado")

        state.shared_resolution_done = True
        state.resolution_done = True
        state.force_resolution_now = False

        state.physical_phase = 6
        state.scene_stage = "desaceleracao"
        state.mary_intent = "desacelerar"
        state.mary_physical_intent = "desacelerar_com_contato"

        state.mary_acao = (
            "Mary permanece colada a Janio, tremendo depois do ápice enquanto recupera o fôlego."
        )

        return True

    return False


def processar_turno(state: MaryState, fala_usuario: str, model: str = None, config: MaryConfig = None) -> Dict[str, Any]:
    if config is None:
        config = MaryConfig()
    if model is None:
        model = config.MODEL_DEFAULT
    
    logger.info(f"=== TURNO {state.turno + 1} INICIADO ===")
    state.turno += 1

    if detectar_reacendimento_pos_aftercare(state, fala_usuario):
    logger.info("Reacendimento pos-aftercare detectado; iniciando novo ciclo fisico")

    state.resolution_done = False
    state.shared_resolution_done = False
    state.force_resolution_now = False

    state.physical_phase = 2
    state.scene_stage = "toque"
    state.mary_intent = "aprofundar_toque"
    state.mary_physical_intent = "explorar_toque"

    state.desire_level = max(state.desire_level, 0.55)
    state.tension_level = max(state.tension_level, 0.35)
    state.connection_level = max(state.connection_level, 0.80)

    state.mary_autonomous_action = (
        "Eu percebo que o clima reacendeu depois do aftercare. "
        "Não trato como primeira vez; volto ao contato com intimidade, provocação leve e memória do que acabou de acontecer."
    )

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
        
        consequencia_travada = detectar_consequencia_da_resposta(state, resposta_final_limpa)
        
        update_final = {}

        update_final = {}

        if not validacao.get("bloqueios"):
            if update_bruto:
                seguro = validar_update(update_bruto, state)
                for k, v in seguro.items():
                    setattr(state, k, v)
                update_final = update_bruto
                logger.info("STATE_UPDATE aplicado (sem bloqueios)")
        else:
            update_corrigido = extrair_state_update(resposta_final) or {}
            if update_corrigido:
                seguro = validar_update(update_corrigido, state)
                for k, v in seguro.items():
                    setattr(state, k, v)
                update_final = update_corrigido
                logger.info("STATE_UPDATE corrigido aplicado")

        if not consequencia_travada:
            atualizar_psique_mary(state, fala_usuario, resposta_final_limpa, config)
            finalizar_resolution_engine(state, resposta_final_limpa)
            sync_state_machine(state, fala_usuario, resposta_final_limpa)
            state.mary_physical_intent = decidir_acao_fisica_mary(state, config)
            state.mary_intent = escolher_intencao_mary(state, config)
            motor_autonomo_mary(state, fala_usuario, config)
        else:
            logger.info("Estado travado por consequência; pulando atualização/sync do turno")

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


def main():
    st.set_page_config(page_title="Mary Roleplay - FSM Refatorado", layout="wide")
    st.title("Mary Roleplay - FSM Narrativa + Filtro (v2.0 Refatorado)")

    state = init_state()
    config = MaryConfig()

    col1, col2 = st.columns([3, 1])

    with col1:
        fala_usuario = st.text_area("Fala/Acao do usuario:", height=100)

    with col2:
        st.markdown("### Controles")
        processar = st.button("Processar turno", use_container_width=True)
        resetar = st.button("Resetar teste", use_container_width=True)

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
            "Debug"
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
            st.markdown("### Detalhes Completos")
            st.json(validacao)

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
    st.subheader("Estado Real Salvo")
    st.json(state.to_dict())


if __name__ == "__main__":
    main()
