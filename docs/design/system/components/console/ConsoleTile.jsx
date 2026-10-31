import React from 'react';

// One sandbox figure. Always plain ink: a figure above its target is stated, never styled as a warning.
// Under 20 turns the foot says "Small sample" in words.
// state: 'default' | 'empty' ("No turns yet") | 'loading' (static skeleton; the title stays)
export function ConsoleTile({ id = 'tile', title, pre, figure, lines = [], rows, closest, spend, foot, state = 'default' }) {
  const hid = id + '-t';
  return (
    <div role="group" aria-labelledby={hid} className="od-tile" data-state={state}>
      <h3 id={hid} className="od-tile__title">{title}</h3>
      {state === 'loading' && <div className="od-tile__sk" aria-hidden="true"><span className="od-sk" style={{ height: 28, width: '45%' }} /><span className="od-sk" style={{ width: '80%' }} /><span className="od-sk" style={{ width: '56%' }} /></div>}
      {state === 'empty' && <p className="od-tile__none">No turns yet</p>}
      {state === 'default' && figure != null && <p className="od-tile__figure">{pre && <span className="od-tile__pre">{pre}</span>}<span className="od-tile__fig">{figure}</span></p>}
      {state === 'default' && lines.map((l) => <p key={l} className="od-tile__line">{l}</p>)}
      {state === 'default' && rows && <dl className="od-tile__rows">{rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>}
      {state === 'default' && closest && <p className="od-tile__closest"><span>Search came closest with:</span>{closest.length ? closest.map((c) => <span key={c}>{c}</span>) : <span>None yet</span>}</p>}
      {state !== 'loading' && spend && <p className="od-tile__spend">{spend}</p>}
      <div className="od-tile__spacer" />
      {state === 'default' && foot && <p className="od-tile__foot">{foot}</p>}
    </div>
  );
}
