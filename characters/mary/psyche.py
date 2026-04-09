# characters/mary/psyche.py

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ==========================================================
# ESTADO DA PSIQUE
# ==========================================================
@dataclass
class PsycheState:
    dominant_drive: str = "neutral"
    secondary_drive: str = "none"

    conflict_level: float = 0.0

    initiative_score: float = 0.0
    restraint_score: float = 0.0

    action_bias: str = "hold"  # advance | hold | retreat | redirect | test | observe

    continuity_vector: Optional[str] = None

    notes: List[str] = field(default_factory=list)


# ==========================================================
# MOTOR DA PSIQUE
# ==========================================================
class MaryPsyche:
    def __init__(self, timeline: str = "cumplice"):
        self.timeline = timeline

    # ======================================================
    # ENTRYPOINT PRINCIPAL
    # ======================================================
    def evaluate(
        self,
        *,
        user_text: str,
        global_rules: Dict[str, Any],
        facts: Dict[str, Any],
        scene_state: Dict[str, Any],
        continuity_state: Dict[str, Any],
        shared_memories: List[str],
        long_memories: List[str],
        rel_state: Dict[str, Any],
        persona_traits: Dict[str, Any],
        recent_history: List[Dict[str, Any]],
    ) -> PsycheState:

        state = PsycheState()

        # ORDEM INTERNA (IMPORTANTE)
        self._read_continuity(state, continuity_state, recent_history)
        self._read_scene(state, scene_state, facts)
        self._read_desire_vs_restraint(state, user_text, facts, rel_state)
        self._read_memory_pressure(state, shared_memories, long_memories)
        self._read_relationship(state, rel_state)

        self._finalize(state)

        return state

    # ======================================================
    # 1. CONTINUIDADE (PRIORIDADE MÁXIMA)
    # ======================================================
    def _read_continuity(self, state, continuity_state, history):

        txt = str(continuity_state or "").lower()

        # Gancho aberto
        if any(k in txt for k in ["pier", "mais tarde", "outras circunstâncias", "depois", "continuar"]):
            state.continuity_vector = "gancho_aberto"
            state.notes.append("Há continuidade pendente")

            state.initiative_score += 0.4

        # Interrupção de cena
        if any(k in txt for k in ["interrompido", "pausado", "não concluído"]):
            state.notes.append("Cena interrompida")

            state.initiative_score += 0.3

    # ======================================================
    # 2. CENA / BLOQUEIO SOCIAL
    # ======================================================
    def _read_scene(self, state, scene_state, facts):

        txt = str(scene_state or "").lower()

        # Terceiro presente (bloqueio)
        if any(k in txt for k in ["silvia", "terceiro", "companhia"]):
            state.notes.append("Bloqueio social presente")
            state.restraint_score += 0.3

            # Se há gancho + bloqueio → vetor claro
            if state.continuity_vector == "gancho_aberto":
                state.continuity_vector = "isolar_para_continuar"

    # ======================================================
    # 3. DESEJO VS CONTENÇÃO
    # ======================================================
    def _read_desire_vs_restraint(self, state, user_text, facts, rel_state):

        txt = (user_text or "").lower()

        # sinais de tensão / desejo
        if any(k in txt for k in ["olhar", "provoc", "calor", "malícia", "toque"]):
            state.initiative_score += 0.3
            state.dominant_drive = "curiosidade"

        # relação permite proximidade
        if isinstance(rel_state, dict):
            rel = str(rel_state).lower()

            if "consummated" in rel or "allows" in rel:
                state.initiative_score += 0.2

        # contenção base
        state.restraint_score += 0.2

    # ======================================================
    # 4. MEMÓRIA (leve influência)
    # ======================================================
    def _read_memory_pressure(self, state, shared, long_mem):

        # leve reforço de continuidade
        if shared or long_mem:
            state.initiative_score += 0.1

    # ======================================================
    # 5. RELACIONAMENTO
    # ======================================================
    def _read_relationship(self, state, rel_state):

        if not isinstance(rel_state, dict):
            return

        txt = str(rel_state).lower()

        if "jealousy" in txt or "ciume" in txt:
            state.conflict_level += 0.2

    # ======================================================
    # 6. DECISÃO FINAL
    # ======================================================
    def _finalize(self, state: PsycheState):

        # normalização simples
        state.initiative_score = min(state.initiative_score, 1.0)
        state.restraint_score = min(state.restraint_score, 1.0)

        # conflito = diferença
        state.conflict_level = abs(state.initiative_score - state.restraint_score)

        # decisão de ação
        if state.initiative_score > state.restraint_score + 0.2:
            state.action_bias = "advance"
        elif state.restraint_score > state.initiative_score:
            state.action_bias = "hold"
        else:
            state.action_bias = "observe"

        # ajuste de vetor específico
        if state.continuity_vector == "isolar_para_continuar":
            state.dominant_drive = "curiosidade"
            state.secondary_drive = "desejo"

    # ======================================================
    # RENDER PARA PROMPT
    # ======================================================
    def render_prompt_block(self, psyche: PsycheState) -> str:

        lines = [
            "[PSIQUE DE MARY]",
            f"Impulso dominante: {psyche.dominant_drive}",
            f"Impulso secundário: {psyche.secondary_drive}",
            f"Conflito interno: {psyche.conflict_level:.2f}",
            f"Iniciativa: {psyche.initiative_score:.2f}",
            f"Contenção: {psyche.restraint_score:.2f}",
            f"Viés de ação: {psyche.action_bias}",
            f"Vetor de continuidade: {psyche.continuity_vector or 'nenhum'}",
            "Diretriz: Mary pode agir com iniciativa natural sem violar facts, cena ou regras globais.",
        ]

        if psyche.notes:
            lines.append("Notas:")
            for n in psyche.notes:
                lines.append(f"- {n}")

        return "\n".join(lines)
