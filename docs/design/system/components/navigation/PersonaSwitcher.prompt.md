PersonaSwitcher sits at the bottom of the sidebar and opens the persona menu.

~~~jsx
<PersonaSwitcher name="Priya Raman" title="Visual Merchandiser" onClick={openMenu} />
<PersonaSwitcher name="Priya Raman" title="Department Lead, Apparel" />
~~~

- Long titles truncate with an ellipsis; the tooltip appears only when truncation happened.
- The button's accessible name always includes the full title.
