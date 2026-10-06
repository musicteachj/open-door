// Turns the capture rows into one self-contained HTML page: the design on the left, the build on
// the right, one row per state. A pure function, so report.test.ts runs it under Vitest.
//
// This is a local development tool, not part of the app. It lives in e2e/, outside src/, so the
// no-raw-colors test (which scans src/) doesn't apply, and the page uses plain neutral hex colors
// in its own inline <style> so it needs no stylesheet, script, or network.

export type ReportRow = {
  title: string
  /** Optional context shown under the title, such as what the capture hovered or pressed. */
  note?: string
  /** Path to the design picture, relative to the report. `null` means it was not captured. */
  design: string | null
  /** Path to the build picture, relative to the report. `null` means it was not captured. */
  build: string | null
  /** Rows are listed in the order given; a heading prints whenever the group changes. */
  group?: string
}

const ESCAPES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}

const escapeHtml = (text: string) => text.replace(/[&<>"']/g, (c) => ESCAPES[c])

const STYLE = `
  body { margin: 0; padding: 24px; font: 14px/1.5 system-ui, sans-serif; color: #222; background: #f6f6f6; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  p.lede { margin: 0 0 20px; color: #555; }
  h2.group { font-size: 16px; margin: 32px 0 8px; padding-bottom: 4px; border-bottom: 2px solid #999; }
  section.row { background: #fff; border: 1px solid #ccc; padding: 12px; margin: 0 0 16px; }
  .title { font-weight: 600; margin: 0 0 2px; }
  .note { color: #555; margin: 0 0 8px; font-size: 13px; }
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-items: start; }
  h3 { font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; color: #555; margin: 8px 0 4px; }
  img { max-width: 100%; height: auto; border: 1px solid #ddd; display: block; }
  .missing { padding: 24px 12px; border: 2px dashed #b00; color: #b00; font-weight: 600; text-align: center; }
`

function cell(label: string, src: string | null, title: string) {
  const picture =
    src === null
      ? '<div class="missing">Not captured</div>'
      : `<img src="${escapeHtml(src)}" alt="${label}: ${escapeHtml(title)}" loading="lazy">`
  return `<div><h3>${label}</h3>${picture}</div>`
}

export function renderReport(rows: ReportRow[]): string {
  const body: string[] = []
  let group: string | undefined
  for (const row of rows) {
    if (row.group !== undefined && row.group !== group) {
      body.push(`<h2 class="group">${escapeHtml(row.group)}</h2>`)
    }
    group = row.group
    body.push(
      `<section class="row"><p class="title">${escapeHtml(row.title)}</p>` +
        (row.note ? `<p class="note">${escapeHtml(row.note)}</p>` : '') +
        `<div class="pair">${cell('Design', row.design, row.title)}${cell('Build', row.build, row.title)}</div></section>`,
    )
  }
  const content = rows.length === 0 ? '<p>Nothing to compare yet.</p>' : body.join('\n')
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Open Door: design and build, side by side</title>
<style>${STYLE}</style>
</head>
<body>
<h1>Open Door: design and build, side by side</h1>
<p class="lede">Local development report. ${rows.length} states. Not committed, not run in CI.</p>
${content}
</body>
</html>
`
}
