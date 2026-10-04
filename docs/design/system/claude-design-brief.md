# Open Door — project brief

AI-first HR help desk, portfolio piece; must read as a real, professional product.
Tagline: "Your open-door policy, now always open."

## Product
- Employees ask HR questions in plain language; answers cite the company handbook.
- Assistant proposes actions; a person confirms them.
- Sensitive topics (harassment, medical) route to a human HR partner, never the AI.
- Managers approve requests; HR works a queue of confidential cases.
- Assistant is the home screen; other pages are for browsing and hand-offs.

## Demo company: Juniper Row (fictional)
120-person apparel and home retailer. Denver HQ, Oakland CA store, Austin TX warehouse.
Visitors explore a private 24-hour sandbox as one of four personas:
- Priya Raman — Visual Merchandiser, Oakland store (salaried employee)
- Mateo Alvarez — Warehouse Associate, Austin warehouse (hourly employee)
- Marcus Bell — Store Manager, Oakland store (manager)
- Dana Whitfield — HR Business Partner, Denver HQ (HR)

## Feel
Calm, trustworthy, safe for sensitive questions. Quiet confidence, generous whitespace, clear hierarchy, nothing shouts. Warm not cute; credible not cold; closer to good banking/healthcare software than social apps. Neutrals do most of the work; color only when it means something. Red = errors only (a denied request is a decision, not an error). No cartoon people, confetti, emoji, nothing cute near sensitive topics.

## Avoid (distinct from user's other apps)
- Palettes: magenta, forest green on warm paper, navy or bright blue, black+lime, dark safety-orange.
- Fonts: Inter, Plus Jakarta Sans, IBM Plex, Newsreader, DM Mono, JetBrains Mono.

## Constraints
- Built with React, Tailwind CSS v4, shadcn/ui (Radix) restyled, Lucide icons. Design so components map to shadcn primitives.
- Desktop at 1440px; layouts collapse sensibly on phone (no mobile mockups).
- Light theme first; tokens structured for dark theme later (semantic names).
- WCAG 2.2 AA: 4.5:1 text contrast, visible focus rings, color never the only signal.
- Voice: calm, plain, specific American English. No exclamation points.

## Design system
Chosen palette: 1c-E aubergine and cinnamon. This project is the Open Door design system: tokens in tokens/, components in components/, guide in readme.md. Assistant Home.dc.html is the decision record.

## Process
One screen at a time.
