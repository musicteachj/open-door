Button is the only clickable action control; use primary for the one confirming action on a view, secondary for alternatives, ghost for low-emphasis actions, destructive only where something can't be undone.

~~~jsx
<Button iconRight="arrow-right" type="submit">Ask</Button>
<Button variant="secondary">Edit dates</Button>
<Button variant="ghost">View source</Button>
<Button variant="destructive" icon="trash-2">Withdraw request</Button>
<Button variant="secondary" size="sm" icon="rotate-ccw">Retry</Button>
~~~

- One primary per view. A person confirms what the assistant proposes, so Confirm is usually the primary.
- Focus is always the aubergine ring, including on destructive buttons.
- Destructive pairs red with an icon and a specific verb. A denied request is not destructive or an error.
- Labels are verbs in sentence case, no exclamation points.
