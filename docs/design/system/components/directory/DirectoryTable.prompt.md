DirectoryTable renders the people list on the Directory page with all its states.

~~~jsx
<DirectoryTable people={results} shown={shown} onShowMore={() => setShown(shown + 50)} youId={me.id}
  query={q} onClear={() => setQ('')} onOpen={(p) => navigate('/directory/' + p.id)} />
~~~

- Empty copy: No one matches “Jordn”. with a Clear search button. With filters only: No one matches these filters. with Clear filters.
- Sorted by last name.
- Page header shows "120 people", or "44 of 120 people" while searching or filtering.
