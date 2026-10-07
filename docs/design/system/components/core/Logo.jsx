import React from 'react';

export function Logo({ org = 'Juniper Row', showWordmark = true, size = 32 }) {
  return (
    <div className="od-logo">
      {size <= 16 ? (
        <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" style={{ flex: 'none' }}>
          <rect width="16" height="16" rx="4.5" style={{ fill: 'var(--primary)' }} />
          <path d="M4 4H9.5A1.5 1.5 0 0 1 11 5.5V16H4z" style={{ fill: 'var(--surface)' }} />
          <path d="M5 5L8 6V15L5 16z" style={{ fill: 'var(--primary)' }} />
        </svg>
      ) : (
        <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" style={{ flex: 'none' }}>
          <rect width="32" height="32" rx="9" style={{ fill: 'var(--primary)' }} />
          <path d="M9 8H20a3 3 0 0 1 3 3V32H9z" style={{ fill: 'var(--surface)' }} />
          <path d="M11 10L17.5 12.5V29.5L11 32z" style={{ fill: 'var(--primary)' }} />
        </svg>
      )}
      {showWordmark && (
        <div className="od-logo__text">
          <span className="od-logo__name">Open Door</span>
          {org && <span className="od-logo__org">{org}</span>}
        </div>
      )}
    </div>
  );
}
