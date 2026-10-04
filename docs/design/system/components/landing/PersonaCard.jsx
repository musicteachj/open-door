import React from 'react';
import { Icon } from '../core/Icon.jsx';

export function PersonaCard({ name, role, location, prompt, initials, status = 'idle', disabled = false,
  onSelect, startLabel, startingLabel = 'Setting up Juniper Row\u2026', className = '', ...rest }) {
  const starting = status === 'starting';
  const first = name.split(' ')[0];
  const ini = initials || name.split(' ').map((w) => w[0]).join('').slice(0, 2);
  const cls = ['od-persona-card', starting ? 'od-persona-card--starting' : '', className].filter(Boolean).join(' ');
  return (
    <button type="button" className={cls} disabled={disabled || starting} aria-busy={starting}
      aria-label={starting ? 'Starting a sandbox as ' + name : 'Start a sandbox as ' + name + ', ' + role + ', ' + location + '. ' + prompt}
      onClick={() => onSelect && onSelect()} {...rest}>
      <span className="od-persona-card__avatar" aria-hidden="true">{ini}</span>
      <span className="od-persona-card__name">{name}</span>
      <span className="od-persona-card__role">{role}</span>
      <span className="od-persona-card__loc"><Icon name="map-pin" size={14} />{location}</span>
      <span className="od-persona-card__rule" aria-hidden="true"></span>
      <span className="od-persona-card__prompt">{prompt}</span>
      <span className="od-persona-card__cta">
        {starting
          ? <><Icon name="loader-circle" size={16} strokeWidth={2} className="od-spin" style={{ color: 'var(--primary)' }} /><span className="od-persona-card__starting">{startingLabel}</span></>
          : <>{startLabel || 'Start as ' + first}<Icon name="arrow-right" size={16} strokeWidth={2} /></>}
      </span>
    </button>
  );
}
