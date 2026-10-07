SearchResultRow lists matches under a status line ("3 sections match “overtime”"). With no matches, use the directory's empty pattern: No sections match “dental plan.” with Clear search (secondary) and Ask the assistant (ghost).

~~~jsx
<ul role="list" className="od-sec-list">
  <SearchResultRow num="3.2" title="Overtime" group="Company handbook" excerpt="Hourly staff are paid overtime at 1.5 times their regular rate…" match="overtime" applies="Hourly staff" appliesToYou updated="Sep 12, 2026" />
</ul>
~~~
