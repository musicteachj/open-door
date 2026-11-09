# 0022. On AWS, the API reaches Claude through the Claude API, not Amazon Bedrock

Status: Accepted · Date: 2026-11-05

## Context

Open Door will run on AWS (Phase 9, held). Claude models are offered both by Anthropic's own
Claude API and by Amazon Bedrock. AI-GOVERNANCE.md left the choice to Phase 8, as part of the
deployed data path.

- **Everything measured so far ran on the Claude API:** every eval run, the model comparison
  behind ADR 0018, and the recorded fixtures CI replays.
- **The code relies on the Claude API's request shape and features:** the pinned model IDs, the
  effort setting, the server-side fallback on a refusal, the refusal's stop details (the console
  stores their category), prompt caching, and the SDK's retries.
- **Bedrock's appeal is real:** traffic and billing stay inside AWS, and access is granted by IAM
  roles instead of an API key.

## Decision

- **The API calls the Claude API** (`api.anthropic.com`) over TLS, with the key held in the
  deploy's secret store (Phase 9 sets it up). Voyage (handbook search embeddings) and Cloudflare
  (Turnstile's check) are the other two outbound destinations; nothing else leaves the task.
- **AI-GOVERNANCE.md records the choice** with what goes to each vendor (unchanged from Phase 7's
  list) and Anthropic's retention and training terms, which already cover the Claude API. The rest
  of the deployed data path on AWS is written in Phase 9.

## Rejected alternatives

- **Amazon Bedrock:** its model IDs differ, and each feature the code uses would have to be checked
  there and the comparison and the full set re-run before switching, for a portfolio demo whose
  data is fictional and deleted within a day. Revisit if a real deployment needs its traffic kept
  inside AWS.
- **Both, behind a switch:** two request paths to test and keep recorded, for no measured benefit.

## Consequences

- The production task needs outbound HTTPS to three hosts (Anthropic, Voyage, Cloudflare). Phase 9
  sets up that egress.
- `ANTHROPIC_API_KEY` stays a secret in Phase 9's secrets contract, rotated by replacing it in the store
  and restarting the tasks.
- The model pins and the eval rules (CLAUDE.md, "Model IDs are pinned") apply unchanged.
