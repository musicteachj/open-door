# Assistant home UI kit

The Open Door app shell and assistant home for Priya Raman (Visual Merchandiser, Oakland store), built from the components in /components.

- AppShell.jsx: sidebar (Logo, NavItem list, PersonaSwitcher) and main area.
- AssistantHome.jsx: greeting, Composer, TryAskingList, and the right rail (SandboxIndicator, GlanceList).
- kit.css: shell layout only. Under 1100 px the rail moves below the content; under 760 px the sidebar becomes a top bar with horizontal nav.

Interactions: type in the composer, pick a Try asking row to fill it, tab through everything to see focus. The answer view isn't designed yet, so sending shows the inline error and Retry clears it. Add ?title=Department%20Lead,%20Apparel to the URL to test persona title truncation.

Source: Assistant Home.dc.html, option 4a.
