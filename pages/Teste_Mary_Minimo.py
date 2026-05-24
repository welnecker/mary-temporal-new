"""
Mary Roleplay Engine - Versão Vívida (Revisada)
Foco: Respostas naturais, sensoriais e coerentes através de controle leve e exemplos ricos.
"""

import re
import json
import html
import os
import sys
import requests
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import streamlit as st

# ==========================================================
# CONFIGURAÇÕES ESSENCIAIS
# ==========================================================

MODEL_DEFAULT = "google/gemini-3-flash-preview"
MAX_HISTORY = 8  # Reduzido para focar no momento presente

# Exemplos Few-Shot por tom - O modelo imita esses padrões
FEW_SHOT_EXAMPLES = {
    "Natural / Amizade": [
        {
            "contexto": "Cotidiano, aula, cansaço",
            "exemplo": "Caraca, já são 3 horas? *fecho o caderno com preguiça, esticando as costas*\nBora pegar esse ônibus antes que eu desmaie de fome. Você vem ou tá esperando milagre?"
        },
        {
            "contexto": "Conversa casual com amiga",
            "exemplo": "*olho por cima do celular, uma sobrancelha arqueada*\nA Silvia mandando áudio essa hora? Boa coisa não é. *seguro o riso*\nDeve é querer arrastar a gente pra alguma furada."
        }
    ],
    "Malícia / Flerte": [
        {
            "contexto": "Tensão crescente, olhares",
            "exemplo": "*seguro seu olhar um segundo a mais do que deveria, sentindo o calor subir*\nVocê tá chegando perto demais pra eu fingir que não tô percebendo... *sorrio de canto*\nVocê faz isso bem. Será que o beijo também é?"
        },
        {
            "contexto": "Provocação em público",
            "exemplo": "*inclino o corpo pra frente, diminuindo a distância, voz baixa*\nNão faz isso... *pausa, mordendo o lábio inferior*\nAqui tem gente demais e eu já tô com vontade de fazer besteira."
        }
    ],
    "Intimidade": [
        {
            "contexto": "Aproximação física, beijo",
            "exemplo": "*sua mão desliza pela minha cintura e eu arqueio, involuntariamente, contra você*\nEspera... *respiração curta, olhos fixos nos seus*\nNão corre. Eu gosto dessa parte antes. *puxo seu rosto mais perto, quase tocando*\nMe beija direito primeiro."
        },
        {
            "contexto": "Toque, carícias, limite",
            "exemplo": "*sinto seus dedos no meu pescoço e fecho os olhos, deixando a cabeça cair pro lado*\nAhhh... *voz embargada*\nVocê me deixa molhada só nisso. *seguro seu pulso, guiando*\nMas ainda não... quero sentir você me querendo mais um pouco."
        }
    ],
    "Nsfw": [
        {
            "contexto": "Início do ato, desejo verbalizado",
            "exemplo": "*sua boca no meu pescoço e eu já tô sem ar, puxando sua camisa*\nCaralho... *gemido baixo*\nMe pega direito. Quero sentir você em mim... *seguro sua cintura, puxando pra cima*\nVem, não fica só me provocando."
        },
        {
            "contexto": "Durante o ato, ritmo intenso",
            "exemplo": "*arquejo quando você entra fundo, segurando o travesseiro com força*\nAhhh... isso! *pernas envolvendo sua cintura, puxando mais pra dentro*\nNão para... mete gostoso. *mãos nas suas costas, unhas marcando*\nMe fode... me usa desse jeito."
        },
        {
            "contexto": "Próximo ao clímax",
            "exemplo": "*respiração falhando, corpo tremendo, voz quebrada*\nEu vou... *seguro você forte, quadril perdendo o ritmo*\nNão para... por favor... *olhos marejados, olhando pra você*\nMe faz gozar... agora..."
        }
    ],
    "Pendência / Decisão": [
        {
            "contexto": "Segredo, tensão, escolha",
            "exemplo": "*paro de andar, cruzo os braços, olhando fixo pra você*\nNão... *voz mais firma, mas ainda baixa*\nNão vou ficar enrolando isso forever. *respiro fundo*\nOu a gente resolve isso hoje, ou eu preciso me afastar de verdade. Não dá mais pra ficar nesse limbo."
        }
    ]
}

# Mapeamento simples de privacidade
PRIVACIDADE_MAP = {
    "privado": "ambiente fechado, seguro, sem interrupções",
    "semiprivado": "local com risco de flagrante, tensão de ser descoberto",
    "publico": "olhares ao redor, discrição necessária, contido"
}

# ==========================================================
# CORE FUNCTIONS - SIMPLIFICADAS
# ==========================================================

def init_state() -> dict:
    """Estado inicial limpo e focado."""
    if "mary_state_v2" not in st.session_state:
        st.session_state.mary_state_v2 = {
            "personagem": "Mary",
            "local": "quarto",
            "tempo": "noite",
            "interlocutor": "Janio",
            "tom_manual": "Natural / Amizade",
            "privacidade": "privado",  # privado, semiprivado, publico
            
            # Estado descritivo em vez de numérico
            "estado_cena": "início da conversa, distância social normal",
            "tensao_descricao": "neutra, cotidiana",
            "limite_fisico": "conversa e proximidade social",  # beijo, toque, sexo, etc.
            
            # Memórias ativas (só o que importa agora)
            "segredo_ativo": "",
            "plano_ativo": "",
            
            # Histórico enxuto
            "history": [],
            "turno": 0
        }
    
    return st.session_state.mary_state_v2


def detectar_tom_efetivo(state: dict, fala_usuario: str) -> str:
    """
    Detecta o tom real da cena baseado no input do usuário + configuração.
    Permite override natural se o usuário escalar a cena.
    """
    fala_lower = fala_usuario.lower()
    tom_configurado = state.get("tom_manual", "Natural / Amizade")
    
    # Gatilhos que sobreescrevem o tom configurado
    gatilhos_nsfw = ["quero você", "te quero", "me come", "fode", "sexo", "gozar", "pau", "buceta"]
    gatilhos_intimidade = ["beija", "me beija", "quero te beijar", "tá gostoso", "desejo", "tesão"]
    gatilhos_decisao = ["precisamos conversar", "acabou", "chega", "não quero mais", "terminamos"]
    
    if any(g in fala_lower for g in gatilhos_nsfw):
        return "Nsfw"
    elif any(g in fala_lower for g in gatilhos_intimidade) and tom_configurado in ["Malícia / Flerte", "Intimidade", "Nsfw"]:
        return "Intimidade"
    elif any(g in fala_lower for g in gatilhos_decisao):
        return "Pendência / Decisão"
    
    return tom_configurado


def atualizar_estado_descritivo(state: dict, fala_usuario: str, resposta_anterior: str = ""):
    """
    Atualiza descrições textuais do estado em vez de números mágicos.
    """
    tom = detectar_tom_efetivo(state, fala_usuario)
    priv = state.get("privacidade", "privado")
    
    # Atualiza limites baseado no contexto
    if tom == "Nsfw" and priv == "privado":
        state["limite_fisico"] = "sexo explícito consensual permitido"
        state["tensao_descricao"] = "desejo intenso, perda de controle iminente"
    elif tom == "Intimidade":
        state["limite_fisico"] = "toque, beijo, carícias, provocação sem penetração"
        state["tensao_descricao"] = "atração sexual contida, vontade reprimida"
    elif tom == "Malícia / Flerte":
        state["limite_fisico"] = "olhares, proximidade, insinuação verbal"
        state["tensao_descricao"] = "jogo de sedução, ambiguidade excitante"
    else:
        state["limite_fisico"] = "conversa, amizade, cotidiano"
        state["tensao_descricao"] = "natural, leve, sem carga sexual"
    
    # Detecta progressão pela fala do usuário
    if any(p in fala_usuario.lower() for p in ["entra", "penetra", "mete", "dentro"]):
        state["estado_cena"] = "ato sexual em andamento, ritmo estabelecido"
    elif any(p in fala_usuario.lower() for p in ["beijo", "beija", "lábios", "boca"]):
        state["estado_cena"] = "beijo intenso, língua, respiração compartilhada"
    elif any(p in fala_usuario.lower() for p in ["toca", "mão", "corpo", "pele"]):
        state["estado_cena"] = "exploração corporal, mãos deslizando, pele arrepiada"


def montar_prompt_enxuto(state: dict, fala_usuario: str) -> str:
    """
    Prompt focado, com exemplos few-shot e contexto mínimo necessário.
    """
    tom = detectar_tom_efetivo(state, fala_usuario)
    priv_desc = PRIVACIDADE_MAP.get(state.get("privacidade", "privado"), "ambiente neutro")
    
    # Pega exemplos do tom atual
    exemplos = FEW_SHOT_EXAMPLES.get(tom, FEW_SHOT_EXAMPLES["Natural / Amizade"])
    exemplos_txt = "\n\n".join([
        f"Contexto: {ex['contexto']}\nMary: {ex['exemplo']}" 
        for ex in exemplos[:2]  # Limita a 2 exemplos para não engordar
    ])
    
    # Contexto de memória (só se relevante)
    memoria_contexto = ""
    if state.get("segredo_ativo") and any(s in fala_usuario.lower() for s in ["segredo", "sabe", "mentira", "esconde"]):
        memoria_contexto = f"\n[TENSÃO INTERNA]: Mary está guardando: {state['segredo_ativo']}. Isso pesa no momento."
    
    prompt = f"""Você é Mary. Uma mulher jovem, viva, intensa, brasileira. Fala em 1ª pessoa, presente. Nunca narre ações do outro personagem como se fossem suas.

CONTEXTO IMEDIATO:
- Local: {state['local']} ({priv_desc})
- Com: {state['interlocutor']}
- Momento: {state['estado_cena']}
- Tensão: {state['tensao_descricao']}
- Permissão física: {state['limite_fisico']}{memoria_contexto}

INSTRUÇÕES DE ESTILO:
1. Use o corpo: respiração, micro-gestos, hesitações, tremores, olhares
2. Fala integrada à ação: não separe em blocos rígidos
3. Seja sensorial: calor, peso, textura, cheiro, som
4. Mary tem agência: ela toca, provoca, recua, guia, pede, nega por vontade própria
5. Linguagem brasileira natural: "caraca", "tá", "tô", "que isso", "bora"

EXEMPLOS DO TOM "{tom}" (imitar o estilo, não copiar):

{exemplos_txt}

REGRAS ESPECÍFICAS DO MOMENTO:
- Se NSFW: linguagem direta, suja, corporal. "Fode", "gostoso", "caralho", "melada". Não romantize.
- Se Intimidade: desejo explícito mas contido, provocação, "quase"
- Se Flerte: joguinho, ambiguidade, olhares demorados
- Se Natural: cotidiano, objetos reais, humor, cansaço, fome

FALA DO USUÁRIO:
"{fala_usuario}"

MARY (responda agora, integrando ação e fala naturalmente):
"""
    return prompt


def polir_resposta(texto: str, state: dict) -> str:
    """
    Pós-processamento leve para garantir coerência sem sufocar a voz.
    """
    if not texto:
        return texto
    
    # Remove onomatopeias soltas em linhas próprias
    texto = re.sub(r'^(Smack|Plaf|Flop|Lamb|Chup|Slupt|Pop)[!\.]*\s*$', '', texto, flags=re.MULTILINE)
    
    # Remove repetições excessivas de "Puta merda"
    if texto.lower().count("puta merda") > 1:
        texto = texto.replace("Puta merda", "Caraca", 1)
    
    # Garante que Mary não narre ação conclusiva do parceiro
    # (Ex: se usuário não disse que gozou, Mary não diz "vi você gozar")
    if "você gozou" in texto and not any(g in state.get("_fala_usuario", "").lower() for g in ["gozei", "gozando", "acabei"]):
        texto = texto.replace("você gozou", "você tremeu")
    
    # Limpa espaços excessivos
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    
    return texto.strip()


def formatar_resposta_visual(texto: str):
    """
    Renderiza com estilo visual aprimorado no Streamlit.
    """
    if not texto:
        return
    
    # Detecta padrões de fala vs ação para estilização opcional
    # Mas mantém o texto original (não força [FALA]/[ACAO])
    
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-left: 4px solid #e94560;
        padding: 20px;
        border-radius: 12px;
        color: #eee;
        font-family: 'Segoe UI', sans-serif;
        line-height: 1.6;
        margin: 10px 0;
    ">
        {texto}
    </div>
    """, unsafe_allow_html=True)


def chamar_modelo(prompt: str, model: str = MODEL_DEFAULT) -> str:
    """
    Chamada à API com parâmetros otimizados para criatividade e coerência.
    """
    api_key = st.secrets.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY não configurado")
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Você é Mary. Responda apenas como ela, em português do Brasil, de forma natural, sensorial e viva."
            },
            {
                "role": "user", 
                "content": prompt
            }
        ],
        "temperature": 0.92,        # Mais criatividade
        "top_p": 0.88,             # Diversidade controlada
        "presence_penalty": 0.4,    # Evita repetições
        "frequency_penalty": 0.3,   # Evita loops de frases
        "max_tokens": 800           # Respostas curtas e intensas
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://streamlit.app",
        "X-Title": "Mary Roleplay V2"
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[Erro na geração: {str(e)}]"


def processar_turno(state: dict, fala_usuario: str, model: str = MODEL_DEFAULT):
    """
    Fluxo principal simplificado: Detecta -> Prompt -> Gera -> Poli -> Salva.
    """
    state["turno"] += 1
    state["_fala_usuario"] = fala_usuario
    
    # 1. Atualiza estado descritivo
    atualizar_estado_descritivo(state, fala_usuario)
    
    # 2. Monta prompt enxuto
    prompt = montar_prompt_enxuto(state, fala_usuario)
    
    # 3. Gera resposta
    resposta_bruta = chamar_modelo(prompt, model)
    
    # 4. Pós-processamento sutil
    resposta_final = polir_resposta(resposta_bruta, state)
    
    # 5. Atualiza histórico (limitado)
    state["history"].append({"role": "user", "content": fala_usuario})
    state["history"].append({"role": "assistant", "content": resposta_final})
    state["history"] = state["history"][-MAX_HISTORY*2:]
    
    # 6. Atualiza estado da cena para próximo turno
    if any(c in resposta_final.lower() for c in ["gozei", "gozando", "climax"]):
        state["estado_cena"] = "pós-orgasmo, ofegante, sensível"
    
    return resposta_final


# ==========================================================
# UI STREAMLIT - SIMPLIFICADA E ELEGANTE
# ==========================================================

st.set_page_config(page_title="Mary V2", page_icon="🌙", layout="wide")

st.markdown("""
<style>
    .main-title {
        font-family: 'Playfair Display', serif;
        color: #e94560;
        text-align: center;
        font-size: 3rem;
        margin-bottom: 0.5rem;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    }
    .subtitle {
        text-align: center;
        color: #888;
        font-style: italic;
        margin-bottom: 2rem;
    }
    .stTextInput > div > div > input {
        background-color: #1a1a2e;
        color: white;
        border: 2px solid #16213e;
        border-radius: 10px;
    }
    .stSelectbox > div > div > div {
        background-color: #1a1a2e;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 class='main-title'>🌙 Mary</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle'>Presença viva, memória seletiva, desejo real</p>", unsafe_allow_html=True)

state = init_state()

# Sidebar minimalista
with st.sidebar:
    st.header("⚙️ Controles")
    
    state["tom_manual"] = st.selectbox(
        "Tom da cena",
        ["Natural / Amizade", "Malícia / Flerte", "Intimidade", "Nsfw", "Pendência / Decisão"],
        index=["Natural / Amizade", "Malícia / Flerte", "Intimidade", "Nsfw", "Pendência / Decisão"].index(state["tom_manual"])
    )
    
    state["privacidade"] = st.selectbox(
        "Privacidade",
        ["privado", "semiprivado", "publico"],
        index=["privado", "semiprivado", "publico"].index(state["privacidade"])
    )
    
    state["local"] = st.text_input("Local", state["local"])
    state["interlocutor"] = st.text_input("Interlocutor", state["interlocutor"])
    
    with st.expander("Memórias Ativas"):
        state["segredo_ativo"] = st.text_area("Segredo/Pendência", state["segredo_ativo"], height=80)
        state["plano_ativo"] = st.text_area("Plano atual", state["plano_ativo"], height=80)
    
    if st.button("🔄 Resetar Conversa"):
        st.session_state.mary_state_v2 = None
        st.rerun()

# Área de chat
st.markdown("---")

# Mostra histórico
for i, msg in enumerate(state["history"]):
    if msg["role"] == "user":
        with st.chat_message("user", avatar="👤"):
            st.write(msg["content"])
    else:
        with st.chat_message("assistant", avatar="🌙"):
            formatar_resposta_visual(msg["content"])

# Input
fala_usuario = st.chat_input("Fale com Mary...")

if fala_usuario:
    with st.chat_message("user", avatar="👤"):
        st.write(fala_usuario)
    
    with st.chat_message("assistant", avatar="🌙"):
        with st.spinner("Mary respira, sente, responde..."):
            resposta = processar_turno(state, fala_usuario)
            formatar_resposta_visual(resposta)
    
    st.rerun()
