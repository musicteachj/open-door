# 0013. A proposal ends its turn normally, and its outcome reaches the next turn's context

Status: Accepted · Date: 2026-10-20

## Context

ADR 0004 says the model proposes and a person confirms: a proposal tool stores a proposal bound
to the person, with an expiry, and a confirm card does the rest. The product design added that the
turn "ends there" and the outcome is "appended to the conversation as a new message". Phase 4
built the loop differently from what that assumed:

- after any tool runs, the loop calls the model again, and a turn's history is written once, when
  it ends with an answer
- every stored `tool_use` must have its `tool_result` in the same write
- a mid-conversation `system` message must be followed by an assistant message
- Opus 5.5 ties its thinking to an unchanged conversation, so nothing stored may be edited

A confirm happens outside any turn, so a message added then would break the last two rules.

## Decision

- **A proposal tool answers the model like any tool:** the engine's result and "A confirm card is
  shown to the person. Nothing is booked until they confirm." The model writes one short closing
  line, and the turn ends as usual. The `proposal` event goes to the browser when the tool
  finishes.
- **The card is built by the server** from the stored engine result, never from the model's text.
- **The outcome reaches the model in the next turn's per-turn context:** one line, made from
  structured data, for each proposal in the conversation that was confirmed, canceled, expired, or
  failed since the last turn. Nothing is ever added to the conversation between turns.
- **A turn that doesn't complete cancels its proposals,** since its history holds only the
  question.
- **One live proposal per conversation:** a new one cancels a pending one.
- **Tool results carry no random IDs,** so recorded eval fingerprints repeat.

## Rejected alternatives

- **Ending the turn the moment the proposal tool returns, with no closing line:** the stored
  history would end on a `tool_result` with no answer, which the history rules refuse, and the
  person would see a card with no words around it.
- **Appending the outcome as a message when the person confirms:** breaks append-only history and
  the "system before assistant" rule, and races any turn that is running.
- **No outcome at all; the model asks a tool:** works, but the model would claim things in the
  next turn ("I've booked it") without having looked.

## Consequences

The model always knows what happened to its proposals before it answers again, at the cost of a
line in the per-turn context. A card can be confirmed while another turn runs. Phase 6's
`propose_open_case` reuses all of this.
