import React from 'react';
import { Icon } from '../core/Icon.jsx';

export function DetailList({ title, icon, note, auditNote, children }) {
  const id = React.useId();
  return (
    <section aria-labelledby={id}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        {icon && <Icon name={icon} size={16} style={{ color: 'var(--ink-muted)' }} />}
        <h2 id={id} style={{ margin: 0, fontSize: 'var(--text-body)', lineHeight: 'var(--leading-body)', fontWeight: 600 }}>{title}</h2>
        {note && <span style={{ fontSize: 'var(--text-small)', lineHeight: 'var(--leading-small)', color: 'var(--ink-muted)' }}>· {note}</span>}
      </div>
      {auditNote && <p className="od-audit-note"><Icon name="eye" size={14} />{auditNote}</p>}
      <dl className="od-details">{children}</dl>
    </section>
  );
}
