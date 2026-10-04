# 0005. Native search-result citations, not prompted sources

Status: Accepted · Date: 2026-09-29

## Context

Every policy claim must cite the handbook. A prompt instruction such as "include your sources" can
be ignored, or the model can cite a section it was never shown.

## Decision

The `search_handbook` tool returns `search_result` content blocks with citations enabled. Claude
cites them through the API's built-in support, and each citation arrives as a
`search_result_location` with the source, title, and exact quoted text. This is generally available
on every current model with no beta header (checked 2026-09-29).

## Rejected alternatives

- **Prompted citations:** unverifiable and easy to invent.
- **Structured output with a citations field:** the API does not allow citations together with
  `output_config.format`, and it would give up streamed prose.

## Consequences

The UI can link every citation to the exact passage. The assistant's turn uses free text plus
citations; only the guard uses structured output. The eval can check citations deterministically
against what was retrieved.
