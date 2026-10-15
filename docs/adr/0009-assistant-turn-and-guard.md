# 0009. Each turn is screened by a guard first, and fails closed

Status: Accepted · Date: 2026-10-14

## Context

The assistant answers employees in plain language, so some messages will be about a crisis or a
sensitive workplace concern. Others will try to talk the model out of its rules. Invariant 6 says
sensitive topics go to humans and crisis text is never generated. Invariant 1 says the model never
decides who can see what. The main model can't be trusted to notice either case on its own, and
it costs too much to ask it twice.

## Decision

Every message goes to a small, fast guard model (`claude-haiku-5-5`, effort `low`, structured
output) before the main model sees it:

- **Crisis** (self-harm or a threat of violence): fixed, human-written text with the 988 Lifeline,
  911, the EAP, and how to reach HR. The main model is never called, and the message never enters
  the model's history.
- **Sensitive:** the main model answers with an operator note (don't counsel, explain
  confidentiality, point to HR), and a fixed escalation panel follows.
- **Suspected injection:** not blocked. The model gets a warning note, and the flag is recorded.
  The guard is advice, not the security boundary: the tools take the actor from the session and
  can't return what the asker isn't allowed to see.
- **The guard fails** (an error, a refusal, invalid output, or no answer in 4 seconds): fail
  closed. The assistant says it can't answer right now and how to reach HR, without calling the
  main model.

## Rejected alternatives

- **No guard; the system prompt asks the main model to notice:** it can be argued out of it, and a
  crisis would get generated text.
- **Hard-block suspected injections:** the guard's false alarms would refuse real questions, and
  blocking adds no protection the tools don't already give.
- **Fail open when the guard is down:** keeps the assistant up during an outage, but a crisis
  message would reach the model unscreened.
- **`claude-haiku-4-5`,** as the product design first named: ten times the price of Haiku 5.5, and
  weaker at following instructions.

## Consequences

Every turn pays a guard call: about $0.0005 and a target of 800 ms at p95. An outage of the guard
model is an outage of the assistant, by design. Phase 6 replaces the sensitive stub with the
confidential-case offer and measures the guard's precision and recall in the escalation eval.

Amended 2026-10-15: because a failed guard can't tell a crisis from anything else, the fixed "can't
answer right now" text also gives 911 and 988. The owner approved it, and it is tied to its hash
like the crisis text. The two budget messages carry the same 911 and 988 line, for the same
reason (a budget stop comes before the safety check, so the message was never screened), and are
approved and hashed the same way.
