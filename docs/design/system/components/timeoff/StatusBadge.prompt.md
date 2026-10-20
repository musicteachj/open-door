StatusBadge shows where a time-off request stands.

~~~jsx
<StatusBadge status="waiting" />   // Waiting for approval
<StatusBadge status="denied" />    // Denied
~~~

- The word is fixed by the status; don't pass custom text.
- Denied is a decision, not an error: never red.
- Put who decided ("Approved by Marcus Bell") under the badge, not inside it.
