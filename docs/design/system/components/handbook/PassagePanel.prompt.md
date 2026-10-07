PassagePanel opens when someone clicks a citation. It isn't modal. Fetch the passage by section and passage id; show state="loading" until it arrives. On open, move focus to the title. Escape or the close button closes it and returns focus to the citation that opened it. While open on the assistant home, it takes the right rail's place.

The eyebrow matches the section page: addenda read "Handbook CA-4.3 · California addendum" (no §); company sections read "Handbook §4.3 · Time off".

~~~jsx
<PassagePanel state="open" eyebrow="Handbook CA-4.3 · California addendum" title="Sick leave" applies="California employees" appliesToYou updated="Sep 12, 2026"
  before="California employees receive 40 hours (5 days)…" cited="You can use sick leave for your own illness…" after="If you know about the need ahead of time…"
  href="/handbook/CA-4.3?passage=p2" onClose={close} />
~~~
