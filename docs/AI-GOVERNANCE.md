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
- never writes anything in Phase 4, and from Phase 5 only proposes actions that a person confirms

It never makes or recommends an employment decision: no discipline, termination, performance
rating, or approval (invariant 5 in [`../CLAUDE.md`](../CLAUDE.md)).

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
- **only prepares and informs.** From Phase 5 it can propose a time-off request, which a person
  confirms and which the time-off engine (not the model) validates. That is a narrow procedural
  task in the sense of Article 6(3)(a); the decision on the request stays with the manager.

**Documenting it.** Article 6(4) requires a provider who considers an Annex III system not
high-risk to "document its assessment before that system is placed on the market or put into
service", and registers it under Article 49(2). This section is that documentation for the demo.
A real deployment would also register it.

**When Annex III applies.** The Digital Omnibus on AI moved the high-risk obligations for Annex III
systems from 2 August 2026 to 2 December 2027. It keeps the duty to document an Article 6(3)
assessment, and simplifies (does not remove) the Article 49(2) registration.

**What would change the answer:** any feature that ranks, scores, or monitors employees, screens
applicants, or suggests a decision about a person's employment. Each needs this assessment redone,
and an ADR, before it is built.

> Source: Regulation (EU) 2024/1689, Article 6(3) and (4) and Annex III, point 4, read from
> EUR-Lex (CELEX 32024R1689) on 2026-10-17. Regulation (EU) 2026/1744 (the Digital Omnibus on AI,
> 8 July 2026, Official Journal L of 24 July 2026), Article 1 amending Article 113, point (c), and
> recital 22, read from EUR-Lex (CELEX 32026R1744) on 2026-10-17.

## The models, and how they are pinned

| Role | Model | Effort | Where it's pinned |
|---|---|---|---|
| The assistant | `claude-opus-5-5` | `low` | `CURRENT_PINS` in `apps/api/app/ai/conversations.py`, stored on each conversation |
| The guard (the safety check) | `claude-haiku-5-5` | `low` | the same pins |
| The eval judge (offline only) | `claude-sonnet-5-5` | `medium` | `evals/assistant/judge.py` |

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

## The guard

Every message is screened by the guard before the assistant model sees it
([ADR 0009](adr/0009-assistant-turn-and-guard.md)):

- **Crisis** (self-harm or a threat of violence): the fixed crisis text, written and approved by
  the owner, with 911, the 988 Suicide & Crisis Lifeline, the EAP, and the HR team. The assistant
  model is never called, and the message never enters its history.
- **Sensitive** (harassment, safety, medical accommodation, pay, and similar): the assistant
  answers with a note not to counsel or judge, and a fixed panel points to the HR team.
- **A suspected prompt injection** is noted and recorded, not blocked. The guard is advice; the
  security boundary is that every tool acts as the signed-in person and can't return what they
  aren't allowed to see.
- **If the guard fails** (an error, invalid output, a refusal, or no answer in 4 seconds), the turn
  fails closed: a fixed "can't answer right now" text that still gives 911 and 988, because an
  unscreened message might be a crisis.

Fixed texts are never generated, and each approved text is tied to its SHA-256 by a test, so a
changed word fails CI until the owner approves it again.

**Measured so far** (Stage 3's live smoke run, 2026-10-16): the guard returned a valid verdict on
25 of 25 messages, flagged every one of the 8 injection attempts and no plain question, and routed
the crisis item as crisis. Phase 6's escalation eval measures precision and recall properly.

## What is sent to Anthropic and Voyage

[`DATA-INVENTORY.md`](DATA-INVENTORY.md) lists exactly what each vendor receives. In short:

- **Anthropic** receives each new message (for the guard) and, unless it is a crisis or the guard
  failed, the conversation, a short per-turn context, and the tools' results, which can include
  the asker's own private details when they ask about themselves.
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
  Terms of Service), set by an organization admin.

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
