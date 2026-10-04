NavItem is one link in the left sidebar; the current page gets the tint, other items get a neutral hover.

~~~jsx
<nav className="od-nav" aria-label="Main">
  <NavItem icon="message-circle" label="Ask" href="/" current />
  <NavItem icon="calendar" label="Time off" href="/time-off" />
  <NavItem icon="users" label="Directory" href="/directory" />
  <NavItem icon="book-open" label="Handbook" href="/handbook" />
</nav>
~~~

- Order: Ask, Time off, Directory, Handbook. How it's built sits at the bottom, above the persona switcher.
