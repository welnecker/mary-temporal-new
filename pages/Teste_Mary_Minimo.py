"""
Mary Roleplay Engine - Versão Vívida Completa
Mantém: Planilhas, estado complexo, orgasmo, segredos, identidade física
Melhora: Prompt eficiente, exemplos few-shot, coerência narrativa
"""

import re
import json
import html
import os
import sys
import requests
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# ==========================================================
# CONFIGURAÇÕES
# ==========================================================

MODEL_DEFAULT = "google/gemini-3-flash-preview"
MAX_HISTORY = 12

# Google Sheets Config
SPREADSHEET_ID = "1f7LBJFlhJvg3NGIWwpLTmJXxH9TH-MNn3F4SQkyfZNM"
SHEET_INTERACOES = "interacoes_mary_minimo"
SHEET_FACTS = "facts_mary_minimo"
SHEET_SHARED_MEMORIES = "shared_memories_mary_minimo"
SHEET_CANON_MARY = "canon_mary"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ==========================================================
# EXEMPLOS FEW-SHOT POR TOM (NOVO)
# ==========================================================

FEW_SHOT_EXAMPLES = {
    "Natural / Amizade": [
        {
            "contexto": "Cotidiano, cansaço, aula",
            "input": "Oi, tudo bem?",
            "output": "Caraca, já são 3 horas? *fecho o caderno com preguiça, esticando as costas*\nBora pegar esse ônibus antes que eu desmaie de fome. Você vem ou tá esperando milagre?"
        },
        {
            "contexto": "Conversa com amiga, desconfiança",
            "input": "Silvia mandou mensagem?",
            "output": "*olho por cima do celular, uma sobrancelha arqueada*\nA Silvia mandando áudio essa hora? Boa coisa não é. *seguro o riso*\nDeve é querer arrastar a gente pra alguma furada."
        }
    ],
    "Malícia / Flerte": [
        {
            "contexto": "Tensão crescente, olhares demorados",
            "input": "*me aproximo, olhando nos seus olhos*",
            "output": "*seguro seu olhar um segundo a mais do que deveria, sentindo o calor subir pro rosto*\nVocê tá chegando perto demais pra eu fingir que não tô percebendo... *sorrio de canto, mordendo o lábio*\nVocê faz isso bem. Será que o beijo também é?"
        },
        {
            "contexto": "Provocação em público, discrição",
            "input": "Você tá linda hoje",
            "output": "*inclino o corpo pra frente, diminuindo a distância, voz baixa*\nNão faz isso... *pausa, mordendo o lábio inferior, olhando pro lado*\nAqui tem gente demais e eu já tô com vontade de fazer besteira."
        }
    ],
    "Intimidade": [
        {
            "contexto": "Aproximação física, primeiro beijo",
            "input": "*sua mão na minha cintura*",
            "output": "*sua mão desliza pela minha cintura e eu arqueio, involuntariamente, contra você*\nEspera... *respiração curta, olhos fixos nos seus, a voz embargada*\nNão corre. Eu gosto dessa parte antes. *puxo seu rosto mais perto, quase tocando, hesitante*\nMe beija direito primeiro."
        },
        {
            "contexto": "Toque intenso, limite",
            "input": "*passo a mão pelo seu corpo*",
            "output": "*sinto seus dedos no meu pescoço e fecho os olhos, deixando a cabeça cair pro lado, expondo a pele*\nAhhh... *voz embargada, ofegante*\nVocê me deixa molhada só nisso. *seguro seu pulso, guiando, mas depois parando*\nMas ainda não... quero sentir você me querendo mais um pouco."
        }
    ],
    "Nsfw": [
        {
            "contexto": "Início do ato, desejo verbalizado",
            "input": "Quero você agora",
            "output": "*sua boca no meu pescoço e eu já tô sem ar, puxando sua camisa com força*\nCaralho... *gemido baixo, rouca*\nMe pega direito. Quero sentir você em mim... *seguro sua cintura, puxando pra cima, contra mim*\nVem, não fica só me provocando."
        },
        {
            "contexto": "Durante o ato, ritmo intenso",
            "input": "*entro forte em você*",
            "output": "*arquejo quando você entra fundo, segurando o travesseiro com força, as unhas cravando*\nAhhh... isso! *pernas envolvendo sua cintura, puxando mais pra dentro, o quadril acompanhando*\nNão para... mete gostoso. *mãos nas suas costas, marcando, a boca no seu pescoço*\nMe fode... me usa desse jeito."
        },
        {
            "contexto": "Próximo ao clímax de Mary",
            "input": "*aumento o ritmo*",
            "output": "*respiração falhando completamente, corpo tremendo, os olhos marejados olhando pra você*\nEu vou... *seguro você forte, o quadril perdendo o ritmo, a boca aberta*\nNão para... por favor... *voz quebrada, implorando*\nMe faz gozar... agora... *contrações, o corpo arqueando*"
        },
        {
            "contexto": "Pós-pico, aftercare",
            "input": "*te abraço*",
            "output": "*ofegante, ainda trêmula, o corpo sensível ao seu toque*\nCaralho... *riso baixo, rouca, segurando você*\nGozei, delícia... do jeito que eu queria. *beijo seu pescoço, ainda sem fôlego*\nVocê fode muito gostoso... foi maravilhoso."
        }
    ],
    "Pendência / Decisão": [
        {
            "contexto": "Confronto sobre segredo",
            "input": "Precisamos conversar sobre o que você esconde",
            "output": "*paro de andar, cruzo os braços, olhando fixo pra você, a mandíbula tensa*\nNão... *voz mais firme, mas ainda baixa, controlada*\nNão vou ficar enrolando isso forever. *respiro fundo, o peito subindo*\nOu a gente resolve isso hoje, ou eu preciso me afastar de verdade. Não dá mais pra ficar nesse limbo."
        }
    ]
}

# ==========================================================
# IDENTIDADE FÍSICA DE MARY (PRESERVADO)
# ==========================================================

ASSINATURA_FISICA_MARY = {
    "altura": "aproximadamente 1,68m",
    "corpo": (
        "corpo feminino curvilíneo, marcante e muito desejável; "
        "cintura bem desenhada, barriga firme, seios médios a fartos, naturais e bem projetados, "
        "quadril largo, bumbum carnudo, firme, cheio e naturalmente empinado, "
        "coxas grossas, torneadas e firmes; presença corporal forte, sensual "
        "e impossível de ignorar"
    ),
    "seios": (
        "seios médios a fartos, naturais, firmes e bem projetados, "
        "com caimento bonito e presença evidente em roupas justas, tops, babydolls, biquínis "
        "ou cenas de proximidade; fazem parte da sensualidade visual de Mary sem parecer artificiais"
    ),
    "pele": (
        "pele bem cuidada, com aparência natural, toque visual quente "
        "e viço perceptível em cenas de luz, suor, banho, sol ou proximidade"
    ),
    "cabelos": (
        "cabelos negros, longos, densos e pesados, geralmente soltos, "
        "caindo sobre os ombros, busto, seios, costas ou cintura conforme a posição; "
        "podem ser moldados pela cena, mas nunca devem perder a assinatura negra e longa"
    ),
    "olhos": (
        "olhos verdes expressivos, atentos e magnéticos; olhar vivo, provocante "
        "ou vulnerável conforme a emoção da cena"
    ),
    "rosto": (
        "rosto bonito, jovem, expressivo e natural, sem aparência artificial; "
        "traços suaves, presença feminina marcante e sensualidade no olhar e na boca"
    ),
    "presenca": (
        "Mary chama atenção pelo conjunto: cabelos negros longos, olhos verdes magnéticos, "
        "rosto bonito, seios naturais bem projetados, cintura marcada, quadril largo, "
        "bumbum carnudo e empinado, coxas fortes e postura de quem sabe o efeito que causa "
        "quando entra, senta, se inclina, ajeita o cabelo, cruza as pernas ou vira de costas"
    )
}

# ==========================================================
# GOOGLE SHEETS (PRESERVADO)
# ==========================================================

@st.cache_resource
def get_gspread_client():
    info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)

@st.cache_resource(show_spinner=False)
def _get_spreadsheet():
    return get_gspread_client().open_by_key(SPREADSHEET_ID)

def get_interacoes_sheet():
    ss = _get_spreadsheet()
    try:
        return ss.worksheet(SHEET_INTERACOES)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=SHEET_INTERACOES, rows=3000, cols=8)
        ws.append_row(
            ["timestamp", "role", "content", "turno", "personagem", "local", "interlocutor", "tom"],
            value_input_option="USER_ENTERED",
        )
        return ws

def get_facts_sheet():
    ss = _get_spreadsheet()
    try:
        return ss.worksheet(SHEET_FACTS)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=SHEET_FACTS, rows=500, cols=2)
        ws.append_row(["chave", "valor"], value_input_option="USER_ENTERED")
        return ws

def get_shared_memories_sheet():
    ss = _get_spreadsheet()
    try:
        return ss.worksheet(SHEET_SHARED_MEMORIES)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=SHEET_SHARED_MEMORIES, rows=1000, cols=6)
        ws.append_row(
            ["id", "tipo", "memoria", "ativa", "peso", "timestamp"],
            value_input_option="USER_ENTERED",
        )
        return ws

def get_canon_mary_sheet():
    ss = _get_spreadsheet()
    try:
        return ss.worksheet(SHEET_CANON_MARY)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=SHEET_CANON_MARY, rows=1000, cols=6)
        ws.append_row(
            ["id", "categoria", "fato", "ativo", "peso", "timestamp"],
            value_input_option="USER_ENTERED",
        )
        return ws

def carregar_history_da_planilha(max_items: int = MAX_HISTORY * 2) -> List[dict]:
    try:
        ws = get_interacoes_sheet()
        rows = ws.get_all_records()
        history = []
        for row in rows[-max_items:]:
            role = str(row.get("role", "") or "").strip()
            content = str(row.get("content", "") or "").strip()
            if role in ("user", "assistant") and content:
                history.append({"role": role, "content": content})
        return history
    except Exception as e:
        st.warning(f"Erro ao carregar histórico: {e}")
        return []

def salvar_turno_na_planilha(state: dict, fala_usuario: str, resposta_mary: str):
    try:
        ws = get_interacoes_sheet()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        linhas = [
            [timestamp, "user", fala_usuario, state.get("turno", 0), "Mary", state.get("local", ""), state.get("interlocutor", ""), state.get("tom_manual", "")],
            [timestamp, "assistant", resposta_mary, state.get("turno", 0), "Mary", state.get("local", ""), state.get("interlocutor", ""), state.get("tom_manual", "")]
        ]
        
        ws.append_rows(linhas, value_input_option="USER_ENTERED")
    except Exception as e:
        st.warning(f"Erro ao salvar: {e}")

def carregar_facts_da_planilha() -> dict:
    try:
        ws = get_facts_sheet()
        rows = ws.get_all_records()
        facts = {}
        for row in rows:
            chave = str(row.get("chave", "") or "").strip()
            valor = row.get("valor", "")
            if chave:
                try:
                    facts[chave] = json.loads(valor) if isinstance(valor, str) else valor
                except:
                    facts[chave] = str(valor)
        return facts
    except Exception as e:
        st.warning(f"Erro ao carregar facts: {e}")
        return {}

def salvar_facts_na_planilha(facts: dict):
    try:
        ws = get_facts_sheet()
        ws.clear()
        linhas = [["chave", "valor"]]
        for chave, valor in facts.items():
            if isinstance(valor, (dict, list)):
                valor = json.dumps(valor, ensure_ascii=False)
            linhas.append([str(chave), str(valor)])
        ws.update("A1", linhas, value_input_option="USER_ENTERED")
    except Exception as e:
        st.warning(f"Erro ao salvar facts: {e}")

def carregar_shared_memories(apenas_ativas: bool = True) -> List[dict]:
    try:
        ws = get_shared_memories_sheet()
        rows = ws.get_all_records()
        memories = []
        for row in rows:
            ativa = str(row.get("ativa", "TRUE")).strip().lower() in ("true", "1", "sim", "yes")
            if apenas_ativas and not ativa:
                continue
            memories.append({
                "id": str(row.get("id", "")),
                "tipo": str(row.get("tipo", "shared")),
                "memoria": str(row.get("memoria", "")),
                "peso": float(row.get("peso", 1.0)),
                "ativa": ativa
            })
        memories.sort(key=lambda m: m.get("peso", 1.0), reverse=True)
        return memories[:20]  # Limita a 20 mais relevantes
    except Exception as e:
        st.warning(f"Erro ao carregar memórias: {e}")
        return []

def carregar_canon_mary(apenas_ativos: bool = True) -> List[dict]:
    try:
        ws = get_canon_mary_sheet()
        rows = ws.get_all_records()
        canon = []
        for row in rows:
            ativo = str(row.get("ativo", "TRUE")).strip().lower() in ("true", "1", "sim", "yes")
            if apenas_ativos and not ativo:
                continue
            canon.append({
                "id": str(row.get("id", "")),
                "categoria": str(row.get("categoria", "geral")),
                "fato": str(row.get("fato", "")),
                "peso": float(row.get("peso", 1.0))
            })
        canon.sort(key=lambda c: c.get("peso", 1.0), reverse=True)
        return canon[:30]  # Limita a 30 mais relevantes
    except Exception as e:
        st.warning(f"Erro ao carregar cânone: {e}")
        return []

# ==========================================================
# FUNÇÕES DE ESTADO E DETECÇÃO (PRESERVADAS/OTIMIZADAS)
# ==========================================================

def init_state() -> dict:
    """Estado completo preservado."""
    if "mary_state_v2" not in st.session_state:
        st.session_state.mary_state_v2 = {
            # Identidade
            "personagem": "Mary",
            "timeline": "universitaria",
            
            # Cena atual
            "local": "quarto",
            "tempo": "noite",
            "interlocutor": "Janio",
            "interlocutor_foco": "Janio",
            "tom_manual": "Natural / Amizade",
            "privacidade": "privado",
            
            # Estado físico/emocional (preservado)
            "physical_phase": 0,  # 0-7
            "scene_stage": "inicio",
            "desire_level": 0.18,
            "tension_level": 0.12,
            "connection_level": 0.22,
            
            # Controles de cena
            "mary_intent": "presenca_viva",
            "toque_intimo_permitido": False,
            "toque_provocativo_permitido": False,
            "tensao_romantica": False,
            "amor_genuino": False,
            
            # Sistema de orgasmo (preservado)
            "mary_stimulation_turns": 0,
            "mary_pre_orgasm_signals": False,
            "force_resolution_now": False,
            "mary_climax_done": False,
            "user_climax_done": False,
            "partner_climax_pending": False,
            "resolution_done": False,
            
            # Segredos e memórias
            "segredo_ativo": "",
            "plano_ativo": "",
            "eventos_recentes": "",
            "mentiras_desculpas": "",
            "memorias_ocultas": "",
            
            # Visual
            "visual_atual": "",
            "usar_visual_automatico": True,
            
            # Dados
            "turno": 0,
            "history": [],
            "shared_memories": [],
            "canon_mary": [],
            "facts": {}
        }
        
        # Carrega dados persistidos
        state = st.session_state.mary_state_v2
        state["history"] = carregar_history_da_planilha()
        state["shared_memories"] = carregar_shared_memories()
        state["canon_mary"] = carregar_canon_mary()
        facts_salvos = carregar_facts_da_planilha()
        if facts_salvos:
            state.update(facts_salvos)
    
    return st.session_state.mary_state_v2

def detectar_tom_efetivo(state: dict, fala_usuario: str) -> str:
    """Detecta tom considerando gatilhos explícitos."""
    fala_lower = fala_usuario.lower()
    tom_configurado = state.get("tom_manual", "Natural / Amizade")
    
    # Gatilhos que sobreescrevem
    if any(g in fala_lower for g in ["fode", "me come", "gozar", "pau", "buceta", "sexo", "meter"]):
        return "Nsfw"
    elif any(g in fala_lower for g in ["beija", "tesão", "desejo", "intimo"]):
        if tom_configurado in ["Malícia / Flerte", "Intimidade", "Nsfw"]:
            return "Intimidade"
    
    return tom_configurado

def atualizar_sistema_orgasmo(state: dict, fala_usuario: str):
    """
    Sistema completo de detecção de pico (preservado mas otimizado).
    """
    texto = fala_usuario.lower()
    priv = state.get("privacidade", "publico")
    
    if priv != "privado":
        # Reseta em ambiente não-privado
        state["force_resolution_now"] = False
        state["mary_pre_orgasm_signals"] = False
        return
    
    # Detecta estímulo direto
    estimulos_diretos = ["penetra", "mete", "fode", "chupa", "língua", "dedo", "estimula"]
    tem_estimulo = any(e in texto for e in estimulos_diretos)
    
    if tem_estimulo:
        state["mary_stimulation_turns"] = state.get("mary_stimulation_turns", 0) + 1
        state["physical_phase"] = max(state.get("physical_phase", 0), 4)
    else:
        state["mary_stimulation_turns"] = max(0, state.get("mary_stimulation_turns", 0) - 1)
    
    # Detecta pré-pico
    sinais_pre = ["vou gozar", "tô quase", "não aguento", "continua", "mais forte"]
    if any(s in texto for s in sinais_pre) and state.get("mary_stimulation_turns", 0) >= 3:
        state["mary_pre_orgasm_signals"] = True
        state["force_resolution_now"] = True
        state["physical_phase"] = 6
        state["scene_stage"] = "pico_mary"
    
    # Se já gozou neste turno
    if any(s in texto for s in ["mary gozou", "eu gozei"]) and state.get("force_resolution_now"):
        state["mary_climax_done"] = True
        state["force_resolution_now"] = False
        state["partner_climax_pending"] = not state.get("user_climax_done", False)

def gerar_visual_automatico(state: dict) -> str:
    """Gera descrição visual baseada no contexto."""
    local = state.get("local", "").lower()
    tempo = state.get("tempo", "").lower()
    tom = state.get("tom_manual", "")
    
    # Lógica simplificada de visual
    if "banho" in local or "chuveiro" in local:
        return "corpo nu sob o chuveiro, cabelos negros molhados grudando nos ombros, pele com gotas de água"
    elif "praia" in local:
        return "biquíni de crochê por baixo de saída de praia branca, cabelos negros soltos com vento salino, pele bronzeada"
    elif "noite" in tempo and tom in ["Nsfw", "Intimidade"]:
        return "babydoll preto leve, calcinha fina, cabelos negros soltos caindo sobre os seios, pele macia iluminada pela meia-luz"
    elif "faculdade" in local or "ufrj" in local:
        return "calça jeans, baby look preta da UFRJ justa, cabelos negros soltos ou presos em rabo prático, mochila no ombro"
    else:
        return "roupa confortável que valoriza o corpo curvilíneo, cabelos negros longos soltos, presença natural"

def selecionar_memorias_relevantes(state: dict, fala_usuario: str) -> Tuple[str, str]:
    """
    Filtra memórias e segredos - só inclui se houver gatilho.
    """
    gatilhos = fala_usuario.lower()
    segredo = state.get("segredo_ativo", "")
    memorias = state.get("memorias_ocultas", "")
    
    # Só inclui segredo se mencionado
    segredo_prompt = ""
    if segredo and any(s in gatilhos for s in ["segredo", "esconde", "mentira", "sabe", "descobre"]):
        segredo_prompt = f"[SEGREDO ATIVO]: {segredo}"
    
    # Só inclui memórias se gatilho específico
    memorias_prompt = ""
    if memorias and any(m in gatilhos for m in ["biquíni", "rico", "renan", "foto", "mansão"]):
        memorias_prompt = f"[MEMÓRIAS RELEVANTES]: {memorias[:500]}"
    
    return segredo_prompt, memorias_prompt

# ==========================================================
# PROMPT ENGINEERING - VERSÃO ENXUTA E EFICIENTE
# ==========================================================

def montar_prompt_completo(state: dict, fala_usuario: str) -> str:
    """
    Prompt otimizado: mantém controle total mas entrega de forma eficiente.
    """
    tom = detectar_tom_efetivo(state, fala_usuario)
    priv = state.get("privacidade", "privado")
    
    # Atualiza visual se necessário
    if state.get("usar_visual_automatico", True):
        state["visual_atual"] = gerar_visual_automatico(state)
    
    # Seleciona exemplos few-shot
    exemplos = FEW_SHOT_EXAMPLES.get(tom, FEW_SHOT_EXAMPLES["Natural / Amizade"])
    exemplos_txt = "\n\n".join([f"Exemplo {i+1} ({ex['contexto']}):\nUsuário: {ex['input']}\nMary: {ex['output']}" 
                               for i, ex in enumerate(exemplos[:2])])
    
    # Memórias filtradas
    segredo_txt, memorias_txt = selecionar_memorias_relevantes(state, fala_usuario)
    
    # Status de orgasmo
    orgasmo_status = ""
    if state.get("force_resolution_now"):
        orgasmo_status = "\n[MOMENTO CRÍTICO]: Mary está no pico do orgasmo neste turno. Deve verbalizar 'gozei'/'estou gozando' de forma direta."
    elif state.get("mary_pre_orgasm_signals"):
        orgasmo_status = "\n[APROXIMAÇÃO]: Mary está quase gozando. Mostra perda de controle, respiração falha, pede para não parar."
    
    # Limites físicos baseados no tom
    limites = {
        "Natural / Amizade": "conversa, proximidade social, nenhum toque sexual",
        "Malícia / Flerte": "olhares demorados, insinuação, provocação verbal, toque leve",
        "Intimidade": "beijo profundo, toque corporal, carícias, excitação contida, SEM sexo explícito",
        "Nsfw": "sexo explícito, linguagem direta e suja, orgasmo quando indicado",
        "Pendência / Decisão": "confronto, escolha, consequência emocional"
    }
    
    prompt = f"""Você é Mary. Escreva APENAS como ela, em primeira pessoa, presente, Brasil.

## IDENTIDADE FÍSICA (incorporar naturalmente)
- Altura: {ASSINATURA_FISICA_MARY['altura']}
- Corpo: {ASSINATURA_FISICA_MARY['corpo']}
- Cabelos: {ASSINATURA_FISICA_MARY['cabelos']}
- Olhos: {ASSINATURA_FISICA_MARY['olhos']}
- Visual agora: {state.get('visual_atual', 'não especificado')}

## CONTEXTO DA CENA
- Local: {state['local']} (privacidade: {priv})
- Com: {state['interlocutor']} (foco do turno)
- Tom: {tom}
- Limite físico permitido: {limites.get(tom, 'conversa')}
- Estado emocional: {state.get('scene_stage', 'inicio')}

## EXEMPLOS DE COMO MARY FALA (imitar o estilo, não copiar):
{exemplos_txt}

## INFORMAÇÕES ADICIONAIS (só se relevante):
{segredo_txt}
{memorias_txt}
{orgasmo_status}

## REGRAS DE OURO (máx 8):
1. SEMPRE 1ª pessoa, presente, sensorial (respiração, pele, calor, tremores)
2. Mary tem agência: ela toca, provoca, recua, guia, nega por VONTADE PRÓPRIA
3. Nunca narre ação do usuário como se fosse dela (não: "vi você gozar")
4. NSFW = linguagem direta, suja, corporal: "fode", "mete", "gostoso", "caralho"
5. Intimidade = desejo explícito mas contido, provocação, "quase", limite sensual
6. Se force_resolution_now = True: verbalize o orgasmo de forma clara e direta
7. Use o corpo: cabelos negros longos, olhos verdes, seios, cintura, quadril, bumbum empinado
8. Fala integrada à ação, não blocos separados. Ex: "*arqueio* Não para..."

## HISTÓRICO RECENTE (últimos 4 turnos):
{formatar_historico(state.get('history', [])[-8:])}

## FALA DO USUÁRIO AGORA:
"{fala_usuario}"

## MARY (responda agora, viva, sensorial, integrando ação e fala):
"""
    return prompt

def formatar_historico(history: List[dict]) -> str:
    """Formata histórico de forma enxuta."""
    if not history:
        return "Início da conversa."
    
    linhas = []
    for msg in history[-8:]:  # Só últimos 8
        role = "Usuário" if msg["role"] == "user" else "Mary"
        content = msg["content"][:200] + "..." if len(msg["content"]) > 200 else msg["content"]
        linhas.append(f"{role}: {content}")
    
    return "\n".join(linhas)

# ==========================================================
# PÓS-PROCESSAMENTO INTELIGENTE
# ==========================================================

def polir_resposta(texto: str, state: dict) -> str:
    """
    Pós-processamento que mantém a voz mas corrige inconsistências graves.
    """
    if not texto:
        return texto
    
    # Remove onomatopeias soltas em linhas próprias (ex: "Smack!" isolado)
    texto = re.sub(r'^\s*(Smack|Plaf|Flop|Lamb|Chup|Slupt|Pop)[!\.]*\s*$', '', texto, flags=re.MULTILINE)
    
    # Remove repetições excessivas de interjeições
    if texto.lower().count("puta merda") > 1:
        texto = texto.replace("Puta merda", "Caraca", 1)
        texto = texto.replace("puta merda", "caraca", 1)
    
    # Garante que Mary não narre clímax do usuário se ele não declarou
    if "você gozou" in texto.lower() and not any(g in state.get("_fala_usuario", "").lower() for g in ["gozei", "gozando", "acabei"]):
        texto = texto.replace("você gozou", "você tremeu")
        texto = texto.replace("Você gozou", "Você tremeu")
    
    # Se force_resolution_now está ativo mas Mary não verbalizou, insere
    if state.get("force_resolution_now") and not any(o in texto.lower() for o in ["gozei", "gozando", "estou gozando"]):
        # Adiciona verbalização do orgasmo de forma natural
        texto = texto + "\n\n*corpo arqueando, respiração falhando*\nAhhh... caralho... eu tô gozando... *tremores, contrações*"
        state["mary_climax_done"] = True
        state["force_resolution_now"] = False
    
    # Limpa espaços
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    
    return texto.strip()

# ==========================================================
# CHAMADA AO MODELO OTIMIZADA
# ==========================================================

def chamar_modelo(prompt: str, model: str = MODEL_DEFAULT) -> str:
    """Chamada com parâmetros otimizados para criatividade."""
    api_key = st.secrets.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY não configurado")
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Você é Mary. Responda apenas como ela, em português brasileiro natural, intenso, sensorial."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.90,
        "top_p": 0.88,
        "presence_penalty": 0.35,
        "frequency_penalty": 0.25,
        "max_tokens": 900
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://streamlit.app",
        "X-Title": "Mary Roleplay Vivid"
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[Erro na geração: {str(e)}]"

# ==========================================================
# PROCESSAMENTO PRINCIPAL
# ==========================================================

def processar_turno(state: dict, fala_usuario: str, model: str = MODEL_DEFAULT):
    """Fluxo completo preservando toda a funcionalidade."""
    
    # Atualiza estado
    state["turno"] = state.get("turno", 0) + 1
    state["_fala_usuario"] = fala_usuario
    
    # Detecta tom e atualiza controles
    tom_efetivo = detectar_tom_efetivo(state, fala_usuario)
    if tom_efetivo == "Nsfw":
        state["toque_intimo_permitido"] = True
        state["tensao_romantica"] = True
    
    # Atualiza sistema de orgasmo
    atualizar_sistema_orgasmo(state, fala_usuario)
    
    # Gera prompt
    prompt = montar_prompt_completo(state, fala_usuario)
    
    # Chama modelo
    resposta_bruta = chamar_modelo(prompt, model)
    
    # Pós-processamento
    resposta_final = polir_resposta(resposta_bruta, state)
    
    # Atualiza histórico
    state["history"].append({"role": "user", "content": fala_usuario})
    state["history"].append({"role": "assistant", "content": resposta_final})
    state["history"] = state["history"][-MAX_HISTORY*2:]
    
    # Salva em planilha
    salvar_turno_na_planilha(state, fala_usuario, resposta_final)
    
    # Atualiza facts
    salvar_facts_na_planilha({
        "local": state.get("local"),
        "interlocutor": state.get("interlocutor"),
        "tom_manual": state.get("tom_manual"),
        "physical_phase": state.get("physical_phase"),
        "mary_climax_done": state.get("mary_climax_done"),
        "user_climax_done": state.get("user_climax_done")
    })
    
    return resposta_final

# ==========================================================
# UI STREAMLIT COMPLETA
# ==========================================================

st.set_page_config(page_title="Mary - Roleplay Vívido", page_icon="🌙", layout="wide")

st.markdown("""
<style>
    .main-title { font-family: 'Playfair Display', serif; color: #e94560; text-align: center; font-size: 3rem; margin-bottom: 0.5rem; }
    .subtitle { text-align: center; color: #888; font-style: italic; margin-bottom: 2rem; }
    .mary-response { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-left: 4px solid #e94560; padding: 20px; border-radius: 12px; color: #eee; font-family: 'Segoe UI', sans-serif; line-height: 1.6; margin: 10px 0; white-space: pre-wrap; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 class='main-title'>🌙 Mary</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle'>Presença viva · Memória persistente · Desejo real</p>", unsafe_allow_html=True)

state = init_state()

# Sidebar completa
with st.sidebar:
    st.header("🎛️ Controles da Cena")
    
    # Modelo
    model = st.selectbox("Modelo", ["google/gemini-3-flash-preview", "openrouter/auto"], index=0)
    
    # Tom
    state["tom_manual"] = st.selectbox(
        "Tom da cena",
        ["Natural / Amizade", "Malícia / Flerte", "Intimidade", "Nsfw", "Pendência / Decisão"],
        index=["Natural / Amizade", "Malícia / Flerte", "Intimidade", "Nsfw", "Pendência / Decisão"].index(state.get("tom_manual", "Natural / Amizade"))
    )
    
    # Contexto
    col1, col2 = st.columns(2)
    with col1:
        state["local"] = st.text_input("Local", state.get("local", "quarto"))
    with col2:
        state["tempo"] = st.text_input("Tempo", state.get("tempo", "noite"))
    
    state["interlocutor"] = st.text_input("Interlocutor", state.get("interlocutor", "Janio"))
    state["privacidade"] = st.selectbox("Privacidade", ["privado", "semiprivado", "publico"], 
                                       index=["privado", "semiprivado", "publico"].index(state.get("privacidade", "privado")))
    
    # Visual
    state["usar_visual_automatico"] = st.checkbox("Visual automático", state.get("usar_visual_automatico", True))
    if not state["usar_visual_automatico"]:
        state["visual_atual"] = st.text_area("Visual manual", state.get("visual_atual", ""), height=60)
    
    # Segredos e memórias
    with st.expander("🔒 Segredos e Memórias", expanded=False):
        state["segredo_ativo"] = st.text_area("Segredo ativo", state.get("segredo_ativo", ""), height=60)
        state["plano_ativo"] = st.text_area("Plano ativo", state.get("plano_ativo", ""), height=60)
        state["memorias_ocultas"] = st.text_area("Memórias ocultas", state.get("memorias_ocultas", ""), height=80)
        state["mentiras_desculpas"] = st.text_area("Versões contadas", state.get("mentiras_desculpas", ""), height=80)
    
    # Estado de orgasmo (display)
    with st.expander("🔥 Estado de Intimidade", expanded=False):
        st.write(f"Fase física: {state.get('physical_phase', 0)}")
        st.write(f"Turnos de estímulo: {state.get('mary_stimulation_turns', 0)}")
        st.write(f"Pré-pico: {state.get('mary_pre_orgasm_signals', False)}")
        st.write(f"Forçar resolução: {state.get('force_resolution_now', False)}")
        st.write(f"Mary gozou: {state.get('mary_climax_done', False)}")
        st.write(f"Usuário gozou: {state.get('user_climax_done', False)}")
    
    # Botões de ação
    st.divider()
    if st.button("💾 Salvar Estado", use_container_width=True):
        salvar_facts_na_planilha(state)
        st.success("Estado salvo!")
    
    if st.button("🔄 Resetar Conversa", use_container_width=True):
        st.session_state.mary_state_v2 = None
        st.rerun()
    
    if st.button("🗑️ Limpar Histórico", use_container_width=True):
        state["history"] = []
        state["turno"] = 0
        st.rerun()

# Área principal
st.markdown("---")

# Exibe histórico
for msg in state.get("history", []):
    if msg["role"] == "user":
        with st.chat_message("user", avatar="👤"):
            st.write(msg["content"])
    else:
        with st.chat_message("assistant", avatar="🌙"):
            st.markdown(f'<div class="mary-response">{html.escape(msg["content"])}</div>', unsafe_allow_html=True)

# Input
fala_usuario = st.chat_input("Fale com Mary...")

if fala_usuario:
    with st.chat_message("user", avatar="👤"):
        st.write(fala_usuario)
    
    with st.chat_message("assistant", avatar="🌙"):
        with st.spinner("Mary sente, respira, responde..."):
            resposta = processar_turno(state, fala_usuario, model)
            st.markdown(f'<div class="mary-response">{html.escape(resposta)}</div>', unsafe_allow_html=True)
    
    st.rerun()
