# 0007. Sessions last as long as the sandbox, with no idle timeout

Status: Accepted · Date: 2026-10-03

## Context

Every visitor gets a sandbox company that is deleted after 24 hours. They sign in by creating the
sandbox, then switch between four fixed personas. There is no password and no other way to sign
back in. If a session ends, the visitor loses the sandbox, and any requests or cases they created
there.

Session standards usually expect an idle timeout. NIST SP 800-63B Rev. 4 says sessions at
assurance level 2 *should* time out after an hour of inactivity. At level 1 an idle timeout is
optional, and both levels allow a 24-hour absolute limit. OWASP ASVS 5.0 (7.1.1 and 7.3.1) asks
that whatever lifetime is chosen be documented and justified.

Source: NIST SP 800-63B Rev. 4, session management and the authenticator assurance levels,
https://pages.nist.gov/800-63-4/sp800-63b/session/, read 2026-10-03.
Source: OWASP ASVS 5.0.0, V7 Session Management,
https://github.com/OWASP/ASVS/tree/v5.0.0/5.0/en, read 2026-10-03.

## Decision

- **A session expires with its sandbox:** 24 hours after the sandbox is created. There's no
  idle timeout. The cookie's `Max-Age` matches, and the server refuses an expired session at
  lookup instead of waiting for cleanup.
- **Switching persona rotates the session.** It issues a new session token and a new CSRF token,
  and the old ones stop working at once.
- **Signing out deletes the session.**
- **Each sandbox creation starts exactly one session.** Creating a new sandbox replaces any
  session the browser already had. Two browsers mean two separate sandboxes, never a shared one.

## Rejected alternatives

- **An idle timeout, such as one hour:** a visitor who steps away would come back to a sandbox
  they can never reach again. That loses their work and gains nothing, because the data is
  fictional and the sandbox is short-lived anyway.
- **A sign-in step to resume a sandbox:** it would mean accounts and credentials, which the demo
  deliberately doesn't have (see `WHAT-THIS-IS-NOT.md`).

## Consequences

The session can't outlive the data it gives access to. If Open Door ever held real employee data,
this decision would need to be revisited. That would come with real sign-in (SSO, a stretch goal),
and with it an idle timeout of an hour or less.
