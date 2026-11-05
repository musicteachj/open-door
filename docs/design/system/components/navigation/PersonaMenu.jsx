import React from 'react';
import { Icon } from '../core/Icon.jsx';

export function PersonaMenu({ personas = [], currentId, onSelect, onSignOut, signOutHref = '/', label = 'View as', note = 'Switching starts a new conversation.', extra, className = '' }) {
  const ref = React.useRef(null);
  React.useEffect(() => { const first = ref.current && ref.current.querySelector('[aria-checked="true"]'); if (first) first.focus(); }, []);
  const move = (e) => {
    const items = Array.from(ref.current.querySelectorAll('[role^="menuitem"]'));
    const i = items.indexOf(document.activeElement);
    if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length].focus(); }
    if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
  };
  return (
    <div className={'od-menu od-persona-menu ' + className} role="menu" aria-label={label} ref={ref} onKeyDown={move}>
      <div className="od-menu__label">{label}</div>
      {personas.map((p) => {
        const cur = p.id === currentId;
        const ini = p.initials || p.name.split(' ').map((w) => w[0]).join('').slice(0, 2);
        return (
          <button type="button" key={p.id} role="menuitemradio" aria-checked={cur} className="od-menu__item od-menu__item--persona" onClick={() => onSelect && onSelect(p)}>
            <span className="od-menu__avatar" aria-hidden="true">{ini}</span>
            <span className="od-menu__text"><span className="od-menu__name">{p.name}</span><span className="od-menu__role">{p.title}</span></span>
            {cur && <Icon name="check" size={16} strokeWidth={2} style={{ color: 'var(--primary)' }} />}
          </button>
        );
      })}
      {note && <p className="od-menu__note">{note}</p>}
      <div role="separator" className="od-menu__sep"></div>
      {extra && <>{extra}<div role="separator" className="od-menu__sep"></div></>}
      <a role="menuitem" href={signOutHref} className="od-menu__item" onClick={(e) => { if (onSignOut) { e.preventDefault(); onSignOut(); } }}>
        <Icon name="log-out" size={16} style={{ color: 'var(--ink-muted)' }} />Sign out
      </a>
    </div>
  );
}
