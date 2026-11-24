# 0024. AI-written answers and summaries carry a machine-readable AI-generated mark

Status: Accepted · Date: 2026-11-20

## Context

Article 50(2) of the EU AI Act requires providers of AI systems that generate text to mark the
output in a machine-readable format, detectable as artificially generated. Until now Open Door told
only people: every answer is labeled as the AI's on screen. Nothing in the output itself told a
machine.

The Commission's code of practice on marking and labeling AI-generated content asks for two layers
of machine-readable marking (Measure 1.1): digitally signed, time-stamped metadata where a format
supports metadata (Sub-measure 1.1.1), and an imperceptible watermark in the content itself, except
for "very short text" under 200 tokens (Sub-measure 1.1.2). Free-form text, such as the text shown
on a website or in a chat, cannot carry metadata, so the watermark alone is enough for it. Text
inside a container such as HTML, PDF, or Word gets both layers. Fingerprinting or logging
(Sub-measure 1.1.3) is optional and never enough alone. The code is voluntary: signatories use it to
show compliance, and anyone else shows adequate alternative means. The marking may be done by the
upstream model provider. A text watermark has to be introduced while the model writes, so Open Door
cannot add one itself through a model provider's API.

Open Door is a portfolio project. Only its author, and the hiring managers and recruiters he shows
it to, will ever see or use it.

> Source: the Code of Practice on Transparency of AI-generated Content (final, published by the
> European Commission on 10 June 2026), Section 1, Measure 1.1 and its glossary, read from the
> Commission's site (digital-strategy.ec.europa.eu, and the code's PDF at
> ec.europa.eu/newsroom/dae/redirection/document/129555) on 2026-11-20, with the Commission's
> Article 50 FAQ read from the same site on the same day.

## Decision

Build a good-faith, machine-readable label in three places, and say plainly what it is not.

- **The API.** A stored answer (`TurnOut`) and a written case summary (`CaseSummaryOut`) carry an
  `aiGenerated` object: the generator ("Open Door AI assistant"), the models that wrote the text
  (read from the turn's own record, or the summary's), and the IPTC digital source type for
  generative content,
  `http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia`. It is set when the model
  wrote any of the text, including the partial text of a failed or stopped turn. A fixed text
  (crisis, budget, "can't answer right now") is written by a person and has no mark, and neither
  does a failed summary.
- **The stream.** `turn.started` carries `"aiGenerated": true`, so a client knows before the first
  word that the words are model-written. It is sent before the safety check runs, so a turn that
  then ends in the crisis text or a budget stop still carries `aiGenerated: true` on that event.
  The stored answer's `aiGenerated` (`TurnOut`) is the authoritative mark.
- **The page.** `data-ai-generated="true"` is on the element that holds model text: the answer, the
  written case summary, and each answer in the walkthrough transcript. Nothing visible changes.

The mark is not the code's digitally signed metadata or its watermark, and Open Door does not sign
the code. A text watermark can only come from the model provider, while the model writes. Many
answers are under the code's 200-token "very short text" line anyway. This is shown practice, not a
claim of compliance. A real product offered in the EU would add signed metadata and rely on the
model provider's watermark.

## Rejected alternatives

- **A visible label only:** it is what exists already, and a machine cannot read it from the output.
- **A watermark in the words** (a pattern or invisible characters Open Door inserts): the code wants
  a watermark robust enough to survive copying and editing, and one added after generation is
  neither. It would also change what a person copies out of an answer.
- **An HTTP header alone:** it labels a response, not the stored text, and it is lost when an answer
  is read from a saved record, a log, or a copy.
- **Digitally signed metadata (the code's Sub-measure 1.1.1):** it needs a signing key and a new
  production secret, for no real user. A demo used only by its author and hiring teams gains nothing
  from it.

## Consequences

- The API schema gains `aiGenerated` on two responses and `aiGenerated` on the `turn.started`
  event; the generated client is regenerated. Nothing the model reads changes: the prompts, tool
  descriptions, and schemas are as they were, so the recorded evals and the scoreboard are
  unaffected.
- The console and its redacted rows are unchanged: they hold no answer text.
- A reload gives the same mark as the live stream, because it is built from the stored record.
- A turn that failed before any model call finished has no recorded model, so its mark (if it has
  partial text) lists no models.
