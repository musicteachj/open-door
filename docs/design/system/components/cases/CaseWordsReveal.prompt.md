# CaseWordsReveal

~~~jsx
<CaseWordsReveal firstName="Priya" words={words} open={open} onToggle={toggle} />
~~~

- Screen 11's confidential treatment: --confidential-tint, lock, no alert style.
- Hidden on every view. Each reveal is recorded and listed in the timeline; status actions stay disabled until the words have been read at least once on this case.
- Disclosure button (aria-expanded, aria-controls). Focus stays on the button; the new timeline row is announced politely.
