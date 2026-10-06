SearchField filters a list as you type; use it at the top of browse pages like the directory.

~~~jsx
<SearchField value={q} onChange={setQ} placeholder="Search by name, title, or email" />
~~~

- Placeholder names the fields searched. Results update as you type; no search button.
- 360 px wide on desktop, full width on phones.
