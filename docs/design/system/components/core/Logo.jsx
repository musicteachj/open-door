import React from 'react';

export function Logo({ org = 'Juniper Row', showWordmark = true, size = 32 }) {
  return (
    <div className="od-logo">
      <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" style={{ flex: 'none' }}>
        <rect width="32" height="32" rx="9" style={{ fill: 'var(--primary)' }} />
        <path d="M13.5 32V17a3 3 0 0 1 3-3h5a3 3 0 0 1 3 3v15z" style={{ fill: 'var(--surface)' }} />
      </svg>
      {showWordmark && (
        <div className="od-logo__text">
          <span className="od-logo__name">Open Door</span>
          {org && <span className="od-logo__org">{org}</span>}
        </div>
      )}
    </div>
  );
}
