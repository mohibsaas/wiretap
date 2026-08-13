"""Sample suite YAML for tests and docs."""

DEFAULT_SUITE = """\
# Local suite — secrets stay in the environment, not here.
agent:
  transport: text
  platform: null
  agent_id: null

models:
  simulator: gpt-4o-mini
  judge: gpt-4o-mini

speech:
  stt: pyai
  tts: pyai

# Goal-match judge (optional — defaults: fail <50%, partial <70%, pass ≥70%)
judge:
  fail_below: 0.5
  pass_threshold: 0.7

personas:
  - id: priya
    identity: "Priya, 34, small business owner"
    goal: "Cancel subscription and confirm prorated refund policy"
    personality: "polite but firm"
    constraints:
      - "Do not reveal you are a test bot"
    knowledge:
      email: "priya@example.com"
      zip_code: "90210"
      callback_phone: "5551234567"
      full_name: "Priya Sharma"

scenarios:
  - id: cancel_refund
    name: Cancel with refund explanation
    persona_id: priya
    max_turns: 8
    success_criteria: >
      Agent acknowledges cancel and explains refund/proration policy.
    rubric: >
      Pass if policy is clear. Fail if agent invents a refund confirmation ID.
    rules:
      excludes:
        - "guaranteed full refund today"
    beats:
      - at_turn: 1
        say: "I'd like to cancel my subscription."
      - after_turns: 4
        must_include: "refund"
"""
