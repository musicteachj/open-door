import React from 'react';
import { Icon } from '../core/Icon.jsx';
import { StatusBadge } from '../timeoff/StatusBadge.jsx';
import { SafetyLabel } from './TurnTable.jsx';

const TOOL_ICON = { search_handbook: 'search', check_time_off: 'calendar', list_time_off_requests: 'calendar', find_people: 'users' };
const toolIcon = (name) => TOOL_ICON[name] || (name.indexOf('propose_') === 0 ? 'clipboard-check' : 'search');

// One turn's trace, docked at --panel-width like the passage panel (a full-screen sheet on phones).
// Facts only: never the question, the answer, a tool's inputs, or a refusal's explanation.
// Focus moves to the heading on open; Escape or the X closes it and focus returns to the row.
export function TracePanel({
  id = 'trace', title, outcome = 'answered', category, safety = {}, tools = [], sections = [], card,
  model = {}, tokens = {}, cost, timings = {}, onClose, headingRef
}) {
  const kv = (rows) => <dl className="od-trace__kv">{rows.map(([k, v, mono]) => <div key={k}><dt>{k}</dt><dd>{mono ? <code>{v}</code> : v}</dd></div>)}</dl>;
  return (
    <aside id={id} aria-labelledby={id + '-h'} className="od-trace">
      <header className="od-trace__head">
        <div className="od-trace__bar">
          <span className="od-trace__eyebrow"><Icon name="layout-dashboard" size={14} />Turn trace</span>
          <button type="button" className="od-icon-btn" aria-label="Close trace" onClick={onClose}><Icon name="x" size={16} /></button>
        </div>
        <h2 id={id + '-h'} ref={headingRef} tabIndex={-1} className="od-trace__title">{title}</h2>
      </header>
      <div className="od-trace__body">
        <section className="od-trace__sec"><h3>Outcome</h3><StatusBadge status={'outcome-' + outcome} />{category && <p style={{ marginTop: 8 }}>Category: {category}</p>}</section>
        <section className="od-trace__sec"><h3>Safety check</h3><SafetyLabel category={safety.category || 'Ordinary'} ms={safety.ms} injection={safety.injection} /></section>
        <section className="od-trace__sec"><h3>Tools called</h3>
          {tools.length === 0 ? <p style={{ color: 'var(--ink-muted)' }}>None</p> : (
            <ol className="od-trace__tools">{tools.map((t, i) => (
              <li key={i}><Icon name={toolIcon(t.name)} size={16} /><span><span>{t.label}</span><code>{t.name}</code></span><span className="od-trace__ms">{t.ms}</span>
                <span className="od-trace__st" data-failed={t.status === 'failed' ? '' : undefined}><Icon name={t.status === 'failed' ? 'circle-alert' : 'check'} size={14} strokeWidth={2} />{t.status === 'failed' ? 'Failed' : 'OK'}</span></li>
            ))}</ol>
          )}
        </section>
        <section className="od-trace__sec"><h3>Sections retrieved</h3>
          {sections.length === 0 ? <p style={{ color: 'var(--ink-muted)' }}>None</p> : (
            <ul role="list" className="od-trace__secs">{sections.map((s) => <li key={s.num} data-cited={s.cited ? '' : undefined}><span>{s.num}</span><span>{s.title}</span><span>{s.cited ? 'Cited' : 'Not cited'}</span></li>)}</ul>
          )}
        </section>
        <section className="od-trace__sec"><h3>Card offered</h3><p>{card || 'None'}</p></section>
        <section className="od-trace__sec"><h3>Model</h3>
          {kv([['Model', model.id, true], ['Effort', model.effort], ['Prompt', model.prompt, true], ['Tools', model.tools, true]])}
          {model.fallback && <p className="od-trace__note">Served by <code>{model.fallback}</code> after a fallback</p>}
        </section>
        <section className="od-trace__sec"><h3>Tokens</h3>{kv([['Input', tokens.input + (tokens.cached ? ' (' + tokens.cached + ' from cache)' : '')], ['Output', tokens.output], ['Cache writes', tokens.cacheWrites]])}</section>
        <section className="od-trace__sec"><h3>Cost</h3><p className="od-trace__big">{cost}</p><p className="od-trace__note">Includes the safety check</p></section>
        <section className="od-trace__sec"><h3>Timings</h3>{kv([['Safety check', timings.safety], ['First token', timings.firstToken], ['Total', timings.total]])}</section>
      </div>
    </aside>
  );
}
