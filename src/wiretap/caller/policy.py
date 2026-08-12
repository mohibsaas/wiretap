"""Legacy single-prompt test agent.

Prefer ``TestAgentOrchestrator`` (Pipecat Flows IR). Kept for direct imports;
``simulate_scenario`` no longer uses this class.
"""

from __future__ import annotations

from wiretap.caller.beats import beat_for_turn
from wiretap.models import Beat, Persona, TurnRecord
from wiretap.providers.llm import complete


def _system_prompt(persona: Persona, success_criteria: str) -> str:
    constraints = "\n".join(f"- {c}" for c in persona.constraints) or "- none"
    knowledge = "\n".join(f"- {k}: {v}" for k, v in persona.knowledge.items()) or "- none"
    return f"""You are a phone caller in a test. Stay in character.
Keep replies short (1-3 sentences). No markdown.

Identity: {persona.identity}
Goal: {persona.goal}
Personality: {persona.personality or "neutral"}
Constraints:
{constraints}
What you know:
{knowledge}
Success looks like: {success_criteria}

When the goal is fully met, reply with exactly: [[HANGUP]]
"""


class Caller:
    def __init__(
        self,
        *,
        persona: Persona,
        success_criteria: str,
        model: str,
        beats: list[Beat] | None = None,
        temperature: float = 0.5,
    ) -> None:
        self.persona = persona
        self.model = model
        self.beats = beats or []
        self.temperature = temperature
        self._caller_turn = 0
        self.history: list[dict[str, str]] = [
            {"role": "system", "content": _system_prompt(persona, success_criteria)}
        ]

    def observe_agent(self, text: str) -> None:
        self.history.append({"role": "user", "content": f"Agent said: {text}"})

    def next_utterance(self) -> tuple[str, bool]:
        self._caller_turn += 1
        beat = beat_for_turn(self.beats, self._caller_turn)

        if beat and beat.say:
            text = beat.say.strip()
            self.history.append({"role": "assistant", "content": text})
            return text, False

        self.history.append(
            {
                "role": "user",
                "content": "Produce your next spoken reply as the caller. Text only.",
            }
        )
        text = complete(model=self.model, messages=self.history, temperature=self.temperature)
        self.history.append({"role": "assistant", "content": text})

        if beat and beat.must_include:
            needle = beat.must_include.lower()
            if needle not in text.lower():
                text = f"{text.rstrip()} {beat.must_include}".strip()
                self.history.append({"role": "assistant", "content": text})

        hangup = "[[HANGUP]]" in text
        return text.replace("[[HANGUP]]", "").strip(), hangup

    def as_turn(self, text: str) -> TurnRecord:
        return TurnRecord(role="user", text=text, intended_text=text)
