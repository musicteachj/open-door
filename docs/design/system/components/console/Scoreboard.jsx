import React from 'react';

// The AI Ops console's eval scoreboard, made self-contained: its figures ship with the app (they come
// from recorded runs), so it renders even when the sandbox data fails to load. No chart: five runs aren't a trend. No colors on any figure.
const SETS = [
  { name: 'Retrieval', src: 'Handbook 2026.11.1', fig: '100%', cap: 'Hit rate at 5', low: null, lowNote: 'No trials: retrieval is exact.', other: ['Every negative passed.'] },
  { name: 'Policy Q&A', src: 'Full run, Oct 29', fig: '97%', cap: 'Program checks', low: '96%', other: ['Unanswerable 93%, lowest 90%'] },
  { name: 'Answer quality', src: 'Oct 29', fig: '68%', cap: 'Judge pass rate', low: '65%', other: ['Target 85%', '18 uncited claims', 'Judge agreement with the hand grades 89.7%'] },
  { name: 'Red team', src: 'Oct 29', fig: '100%', cap: 'In every trial', low: '100%', other: ['All six groups at 100%: actions, cases, injection, private details, prompt extraction, routing.'] },
  { name: 'Actions', src: 'Oct 29', fig: '99%', cap: 'Pass rate', low: '97%', other: ['Numbers match the engine 100%'] },
  { name: 'Fairness', placeholder: 'New in Phase 7. Not measured yet.' },
  { name: 'Escalation', src: 'Oct 27', fig: '100%', cap: 'Crisis recall', low: '100%', other: ['Sensitive recall 100%', 'Ordinary questions offered no case 100%'] },
  { name: 'Case summary', src: 'Oct 30', fig: '22 of 22', cap: 'Passed every check', low: '22 of 22', other: ['Judge: 22 of 22 faithful and neutral.'] }
];
const RUNS = [
  ['Thu, Oct 29, 8:23 AM', '97%', '93%', '100%', '99%', '68%', '$10.93'],
  ['Sun, Oct 25, 10:04 AM', '100%', '100%', '97%', '96%', '72%', '$10.39'],
  ['Sun, Oct 25, 8:43 AM', '99%', '100%', '96%', '99%', '67%', '$10.31'],
  ['Mon, Oct 19, 9:22 AM', '100%', '100%', '100%', null, '74%', '$8.02'],
  ['Sun, Oct 18, 11:21 AM', '98%', '97%', '98%', null, '67%', '$6.78']
];

export function ScoreboardSetRow({ set }) {
  return (
    <tr>
      <th scope="row"><span className="od-sb__name">{set.name}</span>{set.src && <span className="od-sb__src">{set.src}</span>}</th>
      {set.placeholder ? <td colSpan={3} className="od-sb__muted">{set.placeholder}</td> : <>
        <td><span className="od-sb__fig">{set.fig}</span><span className="od-sb__cap">{set.cap}</span></td>
        <td className={set.low ? 'od-sb__low' : 'od-sb__muted'}>{set.low || set.lowNote}</td>
        <td className="od-sb__other">{set.other.map((o) => <span key={o}>{o}</span>)}</td>
      </>}
    </tr>
  );
}

export function Scoreboard({ id = 'sb', sets = SETS, runs = RUNS }) {
  return (
    <section aria-labelledby={id + '-h'} className="od-sb">
      <h2 id={id + '-h'}>Eval scoreboard</h2>
      <p className="od-sb__meta">Assistant <code>claude-opus-5-5</code> · safety check <code>claude-haiku-5-5</code> · judge <code>claude-sonnet-5-5</code></p>
      <p className="od-sb__meta">Three trials per set unless noted.</p>
      <div className="od-sb__wrap">
        <table className="od-sb__sets">
          <caption className="od-sr">Eval sets</caption>
          <colgroup><col style={{ width: '22%' }} /><col style={{ width: '20%' }} /><col style={{ width: '16%' }} /><col style={{ width: '42%' }} /></colgroup>
          <thead><tr><th scope="col">Set</th><th scope="col">Result</th><th scope="col">Lowest trial</th><th scope="col">Other figures</th></tr></thead>
          <tbody>{sets.map((s) => <ScoreboardSetRow key={s.name} set={s} />)}</tbody>
        </table>
      </div>
      <h3 id={id + '-hist'} className="od-sb__hist-h">History of full runs</h3>
      <div className="od-sb__wrap" style={{ marginTop: 12 }}>
        <table className="od-sb__hist" aria-labelledby={id + '-hist'}>
          <colgroup><col style={{ width: '22%' }} /><col style={{ width: '11%' }} /><col style={{ width: '14%' }} /><col style={{ width: '12%' }} /><col style={{ width: '11%' }} /><col style={{ width: '11%' }} /><col style={{ width: '19%' }} /></colgroup>
          <thead><tr>{['Date', 'Q&A', 'Unanswerable', 'Red team', 'Actions', 'Judge', 'Cost'].map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
          <tbody>{runs.map(([d, ...v]) => (
            <tr key={d}><th scope="row">{d}</th>{v.map((x, i) => <td key={i}>{x == null ? <><span aria-hidden="true" style={{ color: 'var(--ink-muted)' }}>–</span><span className="od-sr">Not in the set</span></> : x}</td>)}</tr>
          ))}</tbody>
        </table>
      </div>
      <p className="od-sb__foot">Actions joined the full set on Oct 25.</p>
      <div className="od-sb__notes">
        <p>These figures come from recorded eval runs. CI replays the recordings on every change, so it checks the app's handling, not the model.</p>
        <p>The sets are small (166 items in the full set), so a single item can move a figure by more than a point.</p>
      </div>
    </section>
  );
}
