NavItem is one link in the left sidebar; the current page gets the tint, other items get a neutral hover.

~~~jsx
<nav className="od-nav" aria-label="Main">
  <NavItem icon="message-circle" label="Ask" href="/" current />
  <NavItem icon="calendar" label="Time off" href="/time-off" />
  <NavItem icon="users" label="Directory" href="/directory" />
  <NavItem icon="book-open" label="Handbook" href="/handbook" />
</nav>
~~~

- Order: Ask, Time off, My cases (folder-lock, /my-cases), Directory, Handbook for everyone. Managers add Approvals (with a waiting count). HR adds Cases (with a "3 new" count while new cases exist) and Console after Handbook; HR's own cases are handled by another HR partner, so HR has no My cases item. How it's built sits at the bottom, above the persona switcher.
- Show an item only once its page exists.

~~~jsx
<NavItem icon="clipboard-check" label="Approvals" href="/approvals" count={1} />
<NavItem icon="folder-lock" label="Cases" href="/cases" />
<NavItem icon="layout-dashboard" label="Console" href="/console" />
~~~
