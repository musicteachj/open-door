DetailRow shows one field on a profile; use locked for private fields the viewer may not see.

~~~jsx
<DetailRow label="Manager"><a href="/directory/marcus-bell">Marcus Bell</a></DetailRow>
<DetailRow label="Home address" locked reason="Visible to Leo and HR" />
~~~

- The person and HR see private values. Everyone else sees the locked row.
- Locked rows look calm: muted lock and reason, no red or warning color.
