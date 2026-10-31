# Scoreboard

~~~jsx
<Scoreboard id="console-sb" />
~~~

- Self-contained: the sets, the history of full runs, and the two notes ship with the component. Pass nothing. The DC equivalent is `Scoreboard.dc.html`, the console's scoreboard made self-contained (`<dc-import name="Scoreboard" uid="…">`).
- Bundled, not fetched, so it shows during the console's loading and error states.
- One row per set: headline figure, lowest trial, other figures. Targets are stated as text in ink ("Target 85%"), never colored.
- History is a table, never a chart. "–" with "Not in the set" for screen readers where a set hadn't joined yet.
- No links to code, repositories, or documents.
