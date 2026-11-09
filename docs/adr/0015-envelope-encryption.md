# 0015. Case text and conversation text are encrypted in the API, with a data key per record

Status: Accepted · Date: 2026-10-26

## Context

Handbook §7.2 promises that cases are stored encrypted. The Phase 4 spec and the data inventory
promise that Phase 6 encrypts case narratives and guard-flagged conversation content together.
Three facts shape how:

- **A turn's question is stored when the turn begins, before the guard runs,** and a finished
  turn's row is frozen by a trigger. "Encrypt only flagged turns" would mean saving the question
  later or rewriting it, and later turns that quote it would stay plain.
- **`ai_messages.content` must go back to the model unchanged,** because Opus 5.5 ties its
  signed thinking to the exact conversation.
- **Production will use a managed key service** (AWS KMS, Phase 8 and 9), where every call to
  unwrap a key is a network request.

## Decision

- **Encrypt in the API with AES-256-GCM** (pyca `cryptography`), a fresh 96-bit random nonce each
  time. The database stores only ciphertext and never sees a key.
- **Envelope encryption:** each case and each conversation has its own random data key, stored
  wrapped by a key-encryption key, with that key's ID. One unwrap serves a whole case or a whole
  turn.
- **Associated data binds every ciphertext** to its table, column, sandbox, and row, so a
  ciphertext moved anywhere else fails to decrypt.
- **The scope is case text and all conversation text:** a case's words and summary, and every
  conversation's question, answer, stored messages, tool-call input summaries, and feedback
  reason. Labels and numbers (the guard's category, statuses, tool names, citations, tokens,
  costs) stay readable, for the console. A time-off denial note, a manager's own words, stays
  readable in Phase 6 and is in the backlog.
- **Each encrypted row's ID is made before it's sealed,** since the associated data needs it.
- **Keys come from a `KeyProvider`.** Phase 6 builds a local keyring: a git-ignored file that
  `make setup` writes (refused if anyone but its owner can read it), or an environment variable.
  The newest key wraps, and any key in the ring unwraps, so a key can be rotated. Tests and CI use
  a fixed, obviously fake key that the API refuses outside tests. Phase 8 adds the KMS provider,
  and production then refuses the local one. The API refuses to start without a keyring; there is
  no default key.
- **Encrypted message content is the message's JSON text,** serialized as it is stored today, so
  it decrypts to the same messages, signed thinking included.
- **Existing sandboxes are deleted by the migration,** since nothing is deployed and each expires
  within 24 hours; no plaintext read path is kept.

## Rejected alternatives

- **pgcrypto in the database:** the key would travel in every query, where statement logs and
  errors can capture it.
- **Disk or volume encryption alone:** it protects a stolen disk, not a database login or a
  backup restored elsewhere. Production gets it anyway, from the managed database.
- **One key for everything, with no envelope:** rotating it means re-encrypting every row, and
  with KMS every record would need its own call.
- **A data key per message:** one unwrap per message, which with KMS is a network call each.
- **Flagged turns only:** the question is saved before the verdict, and turns after a flagged one
  can repeat its text.

## Consequences

The conversation store, its display, and its tests change to read and write ciphertext, in its own
stage. Text columns can no longer hold `CHECK` limits on length, so the service enforces them.
Phase 7's console decrypts only what HR may see and shows guard-flagged turns as redacted. Losing
the keyring makes every sandbox unreadable, which for 24-hour demo sandboxes means starting new
ones.

## Amendment (2026-11-05): the KMS provider

Phase 8's planning settles how the KMS provider works, without changing the decision above. **On
2026-11-09 the owner moved the provider itself to Phase 9,** with the rest of the AWS work; until
then production uses the local keyring, passed in its environment.

- **The `KeyProvider` interface stays as it is.** The API still makes each record's data key
  itself; the KMS provider's `wrap` encrypts it with KMS `Encrypt`, and `unwrap` calls `Decrypt`.
  The encryption context carries the same binding as the local provider's associated data (the
  table, the sandbox, and the row), so a wrapped key moved to another row fails to unwrap, and AWS
  logs each use with that context.
- **The stored key ID is the KMS key's ARN,** so rotating the key in KMS (or moving to a new key)
  leaves every older record readable.
- **One call per record, as planned:** a turn unwraps its conversation's key once; a list of
  time-off requests unwraps only the rows that hold a denial note. Calls run off the event loop,
  with a 2-second timeout and two retries; a failure is an error, never a fallback to plaintext.
- **`KEY_PROVIDER` chooses `local` or `kms`; production refuses `local`.** Tests use moto, and the
  local production run uses moto's server, so no AWS account is needed before Phase 9.
- **Rejected: decrypting a keyring once at startup with KMS** and wrapping locally after that. It
  is cheaper, but the key-encryption key would sit in the task's memory, which is what KMS is for
  avoiding.
- **The time-off denial note** moves into the encrypted scope in Phase 8, with a data key per
  request that has one, under the local keyring until the KMS provider exists.
