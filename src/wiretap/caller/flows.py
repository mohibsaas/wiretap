"""Legacy multi-phase caller.

Prefer ``TestAgentOrchestrator`` (Pipecat Flows IR). Kept for direct imports /
older tests; ``simulate_scenario`` no longer uses this class.
"""

from __future__ import annotations

from wiretap.caller.beats import beat_for_turn
from wiretap.models import Beat, Persona, TurnRecord
from wiretap.providers.llm import complete


class FlowCaller:
    """Phase-based caller: one focused task prompt per phase."""

    def __init__(
        self,
        *,
        persona: Persona,
        success_criteria: str,
        model: str,
        phases: list[dict],
        beats: list[Beat] | None = None,
        temperature: float = 0.5,
    ) -> None:
        if not phases:
            raise ValueError("FlowCaller requires at least one phase")
        self.persona = persona
        self.success_criteria = success_criteria
        self.model = model
        self.phases = phases
        self.beats = beats or []
        self.temperature = temperature
        self._phase_idx = 0
        self._turns_in_phase = 0
        self._caller_turn = 0
        self.history: list[dict[str, str]] = [
            {"role": "system", "content": self._phase_prompt()}
        ]

    def _phase_prompt(self) -> str:
        phase = self.phases[self._phase_idx]
        task = phase.get("task") or phase.get("name") or "continue the call"
        return f"""You are a phone caller in a test. Stay in character. Short replies only.
Identity: {self.persona.identity}
Overall goal: {self.persona.goal}
Current phase ({phase.get('id', self._phase_idx)}): {task}
Success overall: {self.success_criteria}
When this phase is done, reply with [[PHASE_DONE]].
When the whole call goal is met, reply with [[HANGUP]].
"""

    def observe_agent(self, text: str) -> None:
        self.history.append({"role": "user", "content": f"Agent said: {text}"})

    def next_utterance(self) -> tuple[str, bool]:
        self._caller_turn += 1
        self._turns_in_phase += 1
        beat = beat_for_turn(self.beats, self._caller_turn)
        if beat and beat.say:
            text = beat.say.strip()
            self.history.append({"role": "assistant", "content": text})
            return text, False

        self.history.append(
            {"role": "user", "content": "Produce your next spoken reply. Text only."}
        )
        text = complete(
            model=self.model,
            messages=self.history,
            temperature=self.temperature,
        )
        self.history.append({"role": "assistant", "content": text})

        hangup = "[[HANGUP]]" in text
        phase_done = "[[PHASE_DONE]]" in text
        clean = text.replace("[[HANGUP]]", "").replace("[[PHASE_DONE]]", "").strip()

        max_turns = int(self.phases[self._phase_idx].get("max_turns") or 4)
        if phase_done or self._turns_in_phase >= max_turns:
            if self._phase_idx < len(self.phases) - 1:
                self._phase_idx += 1
                self._turns_in_phase = 0
                self.history = [{"role": "system", "content": self._phase_prompt()}]
            elif phase_done and not hangup:
                hangup = True

        if beat and beat.must_include and beat.must_include.lower() not in clean.lower():
            clean = f"{clean} {beat.must_include}".strip()

        return clean, hangup

    def as_turn(self, text: str) -> TurnRecord:
        return TurnRecord(role="user", text=text, intended_text=text)
