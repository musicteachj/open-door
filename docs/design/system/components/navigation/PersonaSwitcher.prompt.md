PersonaSwitcher sits at the bottom of the sidebar and opens the persona menu.

~~~jsx
<PersonaSwitcher name="Priya Raman" title="Visual Merchandiser" onClick={openMenu} />
<PersonaSwitcher name="Priya Raman" title="Department Lead, Apparel" />
~~~

- Long titles truncate with an ellipsis; the tooltip appears only when truncation happened.
- The button's accessible name always includes the full title.

- Clicking opens PersonaMenu above it. After a pick, pass busyLabel for the brief switch (under a second), then show a Toast: "Now viewing as Marcus Bell." No confirmation dialog.
