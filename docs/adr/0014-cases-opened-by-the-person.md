# 0014. A case is opened by the person from the HR panel, not proposed by the model

Status: Accepted · Date: 2026-10-26

## Context

The product design planned `propose_open_case(category, summary)`: the model proposes a case, and
a confirm card does the rest, through the proposal flow of ADRs 0004 and 0013. It also planned
`summarize_case(case_id)` as an HR tool in chat, whose turns would get no proposal tools because
it reads text a person wrote.

Writing Phase 6 showed three problems with that:

- **The offer would depend on the model.** Invariant 6 says sensitive topics go to humans. The
  guard, not the model, already decides when a message is sensitive. If the case offer needed a
  tool call, a model that answered badly would offer nothing.
- **The model would write the account HR reads.** Handbook §7.2 promises that the AI writes HR "a
  short, neutral summary of what you wrote". HR should read the person's words, with the AI's
  summary beside them, labeled.
- **Reading case text in chat** needs a way to drop proposal tools for one turn. The tool set is
  sent on every call and pinned per conversation, so that would mean a separate conversation kind
  or tool set, and more to secure.

## Decision

- **The HR panel offers the case.** When the guard flags a message as sensitive or a crisis, the
  `escalation` event's `offerCase` is true, and the panel's own button opens a form in the
  thread: a category, the person's words (prefilled from the flagged message, editable), and what
  is true about a case. "Send to HR" is the person's confirmation. The same form is on the
  "My cases" page.
- **No proposal tool for cases.** The model can't open one, and the prompt tells it to point to
  the button and never to claim a case was opened.
- **The AI summary is written once, when the case opens,** by one model call with no tools that
  sees only the category and the words. It's stored encrypted and shown on HR's case detail.
- **Chat tools read case metadata only** (`get_my_cases`, and `list_cases` for HR). No tool
  returns a case's words or summary, so the main assistant never reads text a person wrote.
- **The words are screened when they're sent,** from the panel's form or the "My cases" page,
  since the form's words may be edited or new. A crisis verdict shows the fixed crisis text and
  writes no summary.
- **HR reads the person's words before changing a case's status.** The summary informs; the
  person's account decides.
- **The handbook says so:** §2.2, §2.3, and §7.2 are reworded, since they say today that raising
  a concern in Open Door opens a case by itself.
- **The next turn's context says a case was opened,** from structured data, as ADR 0013 does for
  proposals.

## Rejected alternatives

- **`propose_open_case` as designed:** the offer depends on the model choosing a tool, and the
  model writes the account.
- **Both the panel and a proposal tool:** two paths to build, test, and keep consistent, for a
  case the panel already offers.
- **`summarize_case` in chat with no proposal tools:** needs a second conversation kind or tool
  set, and puts text a person wrote in front of the main assistant.
- **A "Summarize" button on the case detail:** not written "when a case is opened", and HR waits
  on the AI.

## Consequences

The guard's precision now matters more: a false "sensitive" offers a case to someone asking a
plain policy question. Phase 6's escalation eval measures it, and the route follows the guard's
category alone. The proposal machinery stays time off only. Demo step 6 shows the summary on the
case page rather than in chat, and Dana's starter prompt "Summarize the newest case" is replaced.
ADR 0013's note that `propose_open_case` would reuse it no longer applies.
