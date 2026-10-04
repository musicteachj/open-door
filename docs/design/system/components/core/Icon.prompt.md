Icon renders a Lucide glyph at Open Door's 1.75 stroke; use it anywhere an icon sits beside text.

~~~jsx
<Icon name="calendar" size={18} />
<Icon name="info" size={14} />
~~~

- Sizes: 18 in nav items, 16 in buttons and rows, 14 next to 13 px text.
- Icons are decorative by default (aria-hidden). Pass label only when the icon stands alone.
- In production, import the same names from lucide-react.
