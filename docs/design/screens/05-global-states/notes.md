# 05 · Global states

**Phase:** 2 · **Viewport:** desktop · **Personas:** everyone

Approved on 2026-10-04. The working frames are in
[`../../system/Global States.dc.html`](../../system/Global%20States.dc.html), and the component's
source in [`../../system/components/feedback/`](../../system/components/feedback/). The
screenshots here were rendered from that file.

## Purpose

Explain calmly what happened when a page can't be shown, and offer one way forward.

## Layout

All three use one full-page message, centered: a 28 px title, one plain sentence, and a single
action. There are no icons or illustrations.

- **Session expired** is outside the shell, with only the logo at the top left, because the
  session it belonged to is gone.
- **Not found** and **something went wrong** keep the shell, so the visitor can still navigate,
  with no nav item marked current.

## Components used

Full-page message, Button (primary), Logo, and the app shell.

## States

| State | Screenshot | What differs |
|---|---|---|
| Session expired | `desktop-session-expired.png` | Outside the shell; "Choose who to be" goes to the landing page |
| Not found | `desktop-not-found.png` | A link to Ask |
| Something went wrong | `desktop-error.png` | The request reference and Retry |

## Interactions

- **Session expired** appears whenever the API answers 401 for a signed-in visitor, for example
  after the 24 hours. "Choose who to be" goes to the landing page.
- **Not found** appears for an unknown route, and for a person or page the API reports as not
  found. "Go to Ask" goes to the assistant home.
- **Something went wrong** appears when the API fails unexpectedly. Retry repeats what failed.
  - **The reference is the response's full `X-Request-ID`,** 32 hexadecimal characters, which is
    what the server logs are searched by. The mockup shows 8 characters as a sample. It is in mono
    and selects with one click.
  - **When the shell itself can't load,** because the request for who is signed in fails, this
    page uses the outside-the-shell layout, like session expired.
  - The sentence should not leave "find it:" alone on its own line; a slightly narrower measure
    fixes that.
- **Each title is the page's `h1`,** and focus moves to it when the page appears.

## Copy

- Session expired: "This sandbox has reset." / "Sandboxes last 24 hours. Start a new one to keep
  exploring." / "Choose who to be"
- Not found: "We couldn't find that page." / "Go to Ask"
- Something went wrong: "Something went wrong on our side." / "Try again in a moment. If it keeps
  happening, this reference helps us find it:" / "Reference" and the ID / "Retry"

## Acceptance criteria

- [ ] Matches the screenshots at 1440 px, within the component library's spacing tokens
- [ ] A 401 shows session expired outside the shell, and its button reaches the landing page
- [ ] An unknown route shows not found inside the shell, with no nav item current
- [ ] An unexpected API failure shows the full request ID from `X-Request-ID`, and Retry repeats
      the failed request
- [ ] If the shell can't load, the error page renders outside it
- [ ] Each title is an `h1` and receives focus; axe reports no violations
