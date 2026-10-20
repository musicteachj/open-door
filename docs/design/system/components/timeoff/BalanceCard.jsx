import React from 'react';
import { Icon } from '../core/Icon.jsx';

export function BalanceCard({ id = 'balance', label, hours, days, rows = [], footer = [], source, notice, loading = false }) {
  if (loading) {
    return (
      <div className="od-balance" aria-hidden="true" style={{ minHeight: 292 }}>
        <span className="od-skel" style={{ width: 120 }} />
        <span className="od-skel" style={{ width: 200, height: 32, borderRadius: 8 }} />
        {[100, 100, 100, 70].map((w, i) => <span key={i} className="od-skel" style={{ width: w + '%' }} />)}
      </div>
    );
  }
  return (
    <section className="od-balance" aria-labelledby={id}>
      <div className="od-balance__top">
        <div className="od-balance__head">
          <h2 id={id} className="od-balance__label">{label}</h2>
          {source && <a className="od-source-chip" href={source.href} aria-label={'Source: ' + source.label.replace(' · ', ', ')} data-state={source.state}><Icon name="book-open" size={13} />{source.label}</a>}
        </div>
        <p className="od-balance__figure"><span className="od-balance__big">{hours}</span>{days && <span className="od-balance__days">{days}</span>}</p>
      </div>
      {notice && <p className="od-balance__notice"><Icon name="info" size={16} />{notice}</p>}
      {rows.length > 0 && <dl className="od-ledger">{rows.map((r) => <div key={r.label}><dt>{r.label}</dt><dd>{r.value}</dd></div>)}</dl>}
      {footer.length > 0 && <div className="od-balance__foot">{footer.map((t) => <p key={t}>{t}</p>)}</div>}
    </section>
  );
}
