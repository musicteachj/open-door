FilterToggle is an on/off filter; managers see "My team" in the directory, meaning everyone who reports to them directly or through a lead.

~~~jsx
{isManager && <FilterToggle label="My team" count={44} pressed={team} onChange={setTeam} />}
~~~

- Only render it for people it applies to; don't show it disabled to everyone else.
