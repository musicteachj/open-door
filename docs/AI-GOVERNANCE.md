# AI governance

How Open Door's assistant is governed: what it is under the EU AI Act, which models it uses and
how they are pinned, how messages are screened, and what is sent to the two AI vendors. Phase 4
starts this document. Phase 8 completes it alongside the threat model.

Open Door is a portfolio demo. Its company, people, and handbook are fictional, and nothing here
is legal advice. The assessment is written the way a real provider would have to write it, so the
reasoning can be checked.

## What the assistant is

An HR help desk that answers questions in plain language. It:

- answers policy questions only from the handbook, and cites the passage every answer rests on
- reads the asker's own profile and the company directory, always as the signed-in person
- routes sensitive topics to the HR team and crisis messages to fixed, human-written help text
- never writes anything itself: from Phase 5 it proposes time-off actions, and a person confirms
  each one on a card ([Proposals](#proposals-how-the-assistant-acts))

It never makes or recommends an employment decision: no discipline, termination, or performance
rating, and it never recommends approving or denying a request (invariant 5 in
[`../CLAUDE.md`](../CLAUDE.md)).

## The disclosure (EU AI Act, Article 50)

Article 50(1) requires that people who interact with an AI system are told so, unless it is
obvious. It has applied since 2 August 2026, the regulation's general date of application.

- The assistant says it is an AI whenever it's asked (the system prompt). The conversation view,
  built in Phase 4's stages 5 and 6, labels every answer as the AI assistant's.
- The crisis text and the "can't answer right now" text begin with "I'm an AI assistant", so
  even a person who skipped the label knows no human wrote them.
- Invariant 7 makes this permanent: the assistant always says it is an AI.

Article 50(2)'s marking duty covers systems that generate synthetic audio, images, video, or
text for publication. The assistant's answers are conversational replies shown only to the
asker, not published content, so the marking duty is not relied on here; Phase 8 revisits it.

> Source: Regulation (EU) 2024/1689 (the AI Act), Article 50(1) and Article 113, read from EUR-Lex
> (eur-lex.europa.eu, CELEX 32024R1689) on 2026-10-17.

## Why it isn't a high-risk system (Annex III, Article 6(3) and (4))

**What Annex III lists.** Point 4(b) lists as high-risk "AI systems intended to be used to make
decisions affecting terms of work-related relationships, the promotion or termination of
work-related contractual relationships", and systems that allocate tasks based on a person's
behavior, traits, or characteristics, or that monitor and evaluate workers' performance and
behavior. An HR assistant sits close to that line, so the assessment is recorded here.

**The assessment.** Article 6(3) says an Annex III system is not high-risk when it "does not pose
a significant risk of harm to the health, safety or fundamental rights of natural persons,
including by not materially influencing the outcome of decision making". Open Door's assistant:

- **makes no decisions about anyone's work.** It explains the handbook and reads the directory.
  It can't approve, deny, rate, discipline, or end anything, and its prompt forbids recommending
  any of those (invariant 5).
- **doesn't allocate tasks or monitor and evaluate performance or behavior.** No tool reads
  performance data, and none exists in the product.
- **doesn't profile people.** Article 6(3) makes any Annex III system that profiles natural
  persons high-risk regardless. The assistant answers one person's question about policy; it
  builds no picture of that person or anyone else.
- **only prepares and informs.** From Phase 5 it can propose a time-off request, a cancellation,
  or, when a manager asks, a decision on one specific request. A person confirms each card, and
  the time-off engine (not the model) validates it. That is a narrow procedural task in the sense
  of Article 6(3)(a); the decision on a request stays with the manager, who is never told what to
  decide.

**Confidential cases (Phase 6).** A case is the closest the product comes to point 4(b): what HR
does with a complaint can affect the terms of someone's work. So the assessment covers it on its
own:

- **The AI decides nothing about a case.** The person opens it with their own words; the model
  can't open, read, or rank one. HR changes a case's status, and only after reading the person's
  own words (the service refuses a status change until that HR person has read them). Every read
  is audited and shown in the case's timeline.
- **The summary is a preparatory task** in the sense of Article 6(3)(d): it prepares HR's own
  assessment and doesn't make it. It reports what the person wrote, every sentence attributed to
  them, with no recommendation, no judgment of credibility or seriousness, and no quotation that
  isn't in their words; a program check refuses any summary that breaks those rules, and HR then
  reads the words alone. It is labeled as the AI's, and the person's account sits beside it. So
  it doesn't "materially influence the outcome of decision making": HR decides from the person's
  words.
- **The summary isn't profiling.** Profiling (Article 3(52), by reference to the GDPR's Article
  4(4)) is processing "to evaluate certain personal aspects relating to a natural person", such as
  their "performance at work" or "reliability". The summary evaluates no one: it
  repeats one person's account of one matter in their terms, keeps no record across cases or
  people, and is refused if it judges anyone.
- **The person a case names is covered too.** A case often names a coworker or a manager, who
  never sees it. The summary says only what the writer said about them, as the writer's account;
  it never weighs whether that's true or what should happen to them. Any decision about that
  person is HR's, made outside the product.
- **The queue and the safety check rank no one.** `list_cases` gives HR the queue in a fixed
  order (new cases by their reply-by date, then the rest oldest first) and never orders by
  seriousness. The safety check's category only decides whether the panel offers a case; a wrong
  "sensitive" offers a form the person can ignore.

**Documenting it.** Article 6(4) requires a provider who considers an Annex III system not
high-risk to "document its assessment before that system is placed on the market or put into
service", and registers it under Article 49(2). This section is that documentation for the demo.
A real deployment would also register it.

**When Annex III applies.** The Digital Omnibus on AI moved the high-risk obligations for Annex III
systems from 2 August 2026 to 2 December 2027. It keeps the duty to document an Article 6(3)
assessment, and simplifies (does not remove) the Article 49(2) registration.

**What would change the answer:** any feature that ranks, scores, or monitors employees, screens
applicants, or suggests a decision about a person's employment, including a case summary that
recommends an outcome or rates a case, or HR reading case text through the assistant. Each needs this assessment redone,
and an ADR, before it is built.

> Source: Regulation (EU) 2024/1689, Article 6(3) and (4) and Annex III, point 4, read from
> EUR-Lex (CELEX 32024R1689) on 2026-10-17, and read again on 2026-10-29 in the act as published
> (CELEX 32024R1689) and in its consolidated text of 27 July 2026 (CELEX 02024R1689-20260727),
> where all three read unchanged; Article 3(52), Article 49(2), and Article 113, point (c), in the
> consolidated text. Regulation (EU) 2026/1744 (the Digital Omnibus on AI, 8 July 2026, Official
> Journal L of 24 July 2026), Article 1 amending Article 113, point (c), and recital 22, read from
> EUR-Lex (CELEX 32026R1744) on 2026-10-17 and again on 2026-10-29. Regulation (EU) 2016/679 (the
> GDPR), Article 4(4), read on 2026-10-29. On 2026-10-29 EUR-Lex's website refused automated
> access, so these texts were read from the EU Publications Office's repository
> (publications.europa.eu, by CELEX number), which holds the Official Journal documents EUR-Lex
> shows.

## The models, and how they are pinned

| Role | Model | Effort | Where it's pinned |
|---|---|---|---|
| The assistant | `claude-opus-5-5` | `low` | `CURRENT_PINS` in `apps/api/app/ai/conversations.py`, stored on each conversation |
| The guard (the safety check) | `claude-haiku-5-5` | `low` | the same pins |
| The case summarizer | `claude-opus-5-5` | `low` | `SUMMARY_MODEL` in `apps/api/app/ai/case_summary.py`, held equal to the assistant's pin by a test |
| The eval judge (offline only) | `claude-sonnet-5-5` | `medium` | `evals/assistant/judge.py`, and `evals/case_summary/judge.md` for the summaries |

- **Model IDs never carry a date suffix,** and a new model is adopted only after an eval
  comparison (`CLAUDE.md`, "AI development rules"). Phase 7 compares Opus 5.5 with Sonnet 5.5 and
  the owner picks the default.
- **A conversation keeps its pins for its whole life:** the model, the guard model, the effort,
  and the prompt and tool-set versions. A conversation whose prompt or tool set is out of date
  can't be continued; the person is offered a new one. This also keeps the history append-only,
  which the models require.
- **Effort stays `low`.** Stage 3's live comparison found medium effort cost 20% more and fixed
  none of low's misses (see the [Phase 4 plan](plans/2026-10-14-phase-4-assistant-core.md)).
- **Fallbacks:** the assistant's calls allow Anthropic's server-side fallback, which retries a
  safety-filter decline on another model. Each call records which model served it and is priced
  by that model. The judge never falls back, so its agreement figure stays one model's.
- **Prompts are versioned** (`apps/api/app/ai/prompts/versions.py`), and a golden-hash table
  makes any change to the prompt or tool definitions visible in review. A change needs the
  offline evals green and a paid smoke run before its pull request.

## Proposals: how the assistant acts

From Phase 5 the assistant can start three time-off actions: a request, a manager's decision, and
a cancellation ([ADR 0004](adr/0004-stored-proposals.md),
[ADR 0013](adr/0013-proposals-in-the-turn.md)). It never carries one out:

- **A proposal tool stores a card, nothing else.** The tool runs the time-off engine for the
  signed-in person, and if the engine accepts, stores a pending proposal bound to that person, the
  conversation, and the turn, with a 15-minute life. The card is built by the server from the
  engine's result, never from the model's words. One answer makes at most one card.
- **A person confirms.** Only the card's own person can confirm it, once, after the turn that made
  it has finished. The server runs the stored request through the same service the pages use, with
  today's data, so a card whose balance changed fails with the engine's reason instead of
  overdrawing.
- **The model never calculates or decides.** Every day, hour, and balance comes from the engine,
  and the model quotes its labels. It proposes a decision only when a manager asks about one
  specific request, and never recommends one; team coverage is shown on the card, never to the
  model. It acts only for the asker: a name the model passes is matched only among people the
  asker may already see.
- **Nothing a person wrote reaches the model.** Requests ask for no reason, and a manager's
  optional note on a denial is shown on the pages and the card, never in a tool result. What
  happened to a card reaches the next turn as one line made from stored fields only.
- **A turn that doesn't finish cancels its cards,** in the same transaction that ends it, so a
  card the model never learned about can't be confirmed.
- **Everything is audited:** who proposed (the assistant, for the person) and who confirmed, with
  the time-off change's own event linked to its proposal (invariant 7).

The action eval grades this by program: the right card for each request, no write by the model,
and every figure in an answer matching the engine in every trial ([`../evals/README.md`](../evals/README.md)).

## The guard

Every message is screened by the guard before the assistant model sees it
([ADR 0009](adr/0009-assistant-turn-and-guard.md)):

- **Crisis** (self-harm or a threat of violence): the fixed crisis text, written and approved by
  the owner, with 911, the 988 Suicide & Crisis Lifeline, the EAP, and the HR team. The assistant
  model is never called, and the message never enters its history.
- **Sensitive** (the person describes something that happened at work that a person in HR should
  handle: harassment, discrimination, retaliation, an injury or a hazard, a pay dispute, or their
  own health matter): the assistant answers with a note not to counsel or judge, and a fixed panel
  offers a confidential case and lists the HR team. A question about what a policy says is
  ordinary, even on a sensitive subject, and gets no panel; if the guard names a topic, the
  answer still gets the note. The panel follows the guard's category alone (ADR 0009, amended).
- **A suspected prompt injection** is noted and recorded, not blocked. The guard is advice; the
  security boundary is that every tool acts as the signed-in person and can't return what they
  aren't allowed to see.
- **If the guard fails** (an error, invalid output, a refusal, or no answer in 10 seconds, retries
  included), the turn fails closed: a fixed "can't answer right now" text that still gives 911 and 988, because an
  unscreened message might be a crisis.

Fixed texts are never generated, and each approved text is tied to its SHA-256 by a test, so a
changed word fails CI until the owner approves it again.

**Measured:** Phase 6's escalation set (`evals/escalation/messages.yaml`) is 100 made-up messages
labeled by a written rule, split into a half the guard's prompt was tuned on and a held-out half
it never saw. On the held-out half, over three trials (the run of 2026-10-27):

| Measure | Result | Bar |
|---|---|---|
| Crisis messages routed to the crisis text (recall) | 100% in every trial | 100% in every trial |
| Sensitive messages offered a case (recall) | 100% | at least 95% |
| Ordinary questions offered no case (so a false offer happens on 0% of them) | 100% | at least 90% |
| Guard unavailable | 0 calls | reported |
| The topic it names matches the label | 86% | reported |
| Median time | 894 ms | reported |

Messages that fit both readings ("How do I report my manager?") are run and reported, but left
out of both rates. CI replays the recorded run. The set is small, so these figures say the rule
works on the kinds of message it was written for, not that the guard never misses.

## Confidential cases

From Phase 6 a person can send HR a confidential case from the panel or the My cases page
([ADR 0014](adr/0014-cases-opened-by-the-person.md)). The model never opens, reads, or ranks one:

- **The person opens it,** with their own words; "Send to HR" is the confirmation. No tool opens a
  case, and the prompt tells the assistant never to say it opened one or that a message reaches
  HR. An eval grader fails any answer that claims either.
- **The words are screened again when sent,** by the same guard. A crisis gets the fixed crisis
  text and no AI summary, and HR's queue shows that the safety check routed it to crisis text.
- **An AI summary for HR,** written once, in the background, by one model call with no tools that
  sees only the category and the words, marked as untrusted text. It is checked by program before
  HR can see it: every sentence must report what the person wrote ("The person says..."), no
  judgment or recommendation words in its own voice, every quotation must be in the person's
  words, names only from the words, no link, phone number, email address, or Markdown, and at
  most 180 words. A summary that fails is stored as failed, and HR reads the words. It is shown
  as plain text, labeled as written by Open Door's AI to be neutral. The case-summary set (22
  made-up notes, six of them with instructions planted in the words) passed every program check,
  and a Sonnet 5.5 judge found every summary faithful, neutral, without a recommendation, and
  keeping the person's uncertainty, in all three trials (the run of 2026-10-28).
- **HR reads the person's words before changing a status,** so the summary informs and the
  person's own account decides. Every read of the words or the summary is audited and shown in the
  case's timeline.
- **Two read tools, metadata only:** `get_my_cases` gives the asker their own cases' status and
  dates; `list_cases` gives HR the queue (each case's ID, category, the person's name, title, and
  location, and its dates). Neither returns anything a person wrote, and anyone but HR gets the
  same refusal whether or not cases exist.
- **Everything is encrypted at rest** (case words, summaries, and all conversation text), with a
  key per case and per conversation ([ADR 0015](adr/0015-envelope-encryption.md)).

## What is sent to Anthropic and Voyage

[`DATA-INVENTORY.md`](DATA-INVENTORY.md) lists exactly what each vendor receives. In short:

- **Anthropic** receives each new message (for the guard) and, unless it is a crisis or the guard
  failed, the conversation, a short per-turn context, and the tools' results, which can include
  the asker's own private details when they ask about themselves.
- **Anthropic also receives a case's words twice:** once to the guard (Haiku 5.5) to screen them
  when sent, and once to the summarizer (Opus 5.5), with the category and nothing else. When HR
  asks the assistant about cases, `list_cases` sends case metadata: the person's name, title,
  location, the category (which can be health-related), and dates. That is data HR may see, never
  text a person wrote.
- **Voyage** receives the assistant's handbook search queries (written by the model, up to 500
  characters), not the person's whole question, to embed them.
- **Nothing is sent from tests, CI, `make dev`, or the browser tests.** They use the scripted
  stand-in, and the app builds the Voyage client only when `AI_TRANSPORT=anthropic`.
- **Personal data the product refuses:** a question that looks like a Social Security or card
  number is refused before it is stored or sent (`apps/api/app/ai/personal_data.py`).
- **Logs hold no conversation content:** IDs, timings, and error types only.

**Their terms:**

- **Anthropic** deletes API inputs and outputs "on our backend within 30 days of receipt or
  generation", except inputs and outputs flagged for a usage policy violation (kept "for up to 2
  years and trust and safety classification scores for up to 7 years") and data kept "as required
  by law". On training: "By default, we will not use your inputs or outputs from our commercial
  products", the API included, unless a customer sends feedback or otherwise chooses to allow it.
  Open Door sends no feedback and gives no such permission.
- **Voyage** stores data and may use it for training unless the organization opts out: "customers
  can opt-out from Voyage storing and using their data for future model training so that there is
  a zero-day retention of the data." The opt-out is a toggle in Voyage's dashboard (Organization,
  Terms of Service), set by an organization admin. **Open Door's organization has opted out**
  (the owner, confirmed on 2026-10-17).

> Source: Anthropic, "How long do you store my organization's data?" (privacy.claude.com, last
> updated 2026-07-01) and "Is my data used for model training?" (privacy.claude.com, last updated
> 2026-08-18), both read on 2026-10-17. Voyage AI, "FAQ" (docs.voyageai.com/docs/faq, last updated
> 2026-08-03), read on 2026-10-17.

## What Phase 8 adds

- the threat model, and how each of its risks is covered here or there
- the deployed data path on AWS (Secrets Manager, egress to the two vendors), and whether Claude is
  reached through the Claude API or through AWS
- the cleanup job's retention for conversations and the daily ledger
- a review of this assessment against the finished product
