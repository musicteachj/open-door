import React from 'react';

const STATES = { CA: 'California', CO: 'Colorado', TX: 'Texas' };

/** Builds the label from up to three parts: state, employment type, location. No parts means Everyone. */
export function appliesLabel({ state, type, location } = {}) {
  const st = state ? STATES[state] || state : null;
  if (type && st) return type + ' in ' + st;
  if (type && location) return type + ' at ' + location;
  if (type) return type;
  if (st) return st + ' employees';
  if (location) return location;
  return 'Everyone';
}

export function ApplicabilityBadge({ state, type, location, label, variant = 'chip', className = '' }) {
  const text = label || appliesLabel({ state, type, location });
  if (variant === 'text') return <span className={'od-applies od-applies--text ' + className}><span className="od-applies__value">{text}</span></span>;
  return (
    <span className={'od-applies ' + className}>
      <span className="od-applies__label">Applies to:</span>
      <span className="od-applies__value">{text}</span>
    </span>
  );
}
