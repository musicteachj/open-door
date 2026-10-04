Tooltip shows short supplementary text on hover or focus; use it only to reveal text that is truncated or an icon-only control's name.

~~~jsx
<Tooltip content="Department Lead, Apparel" disabled={!isTruncated}>
  <button>...</button>
</Tooltip>
~~~

- Never put essential information or actions in a tooltip.
- Stays open while hovered, closes on Escape (WCAG 1.4.13).
