import React from 'react';

export function Avatar({ initials, size = 40, muted = false, className = '' }) {
  return (
    <span aria-hidden="true" className={'od-avatar ' + className} data-size={size} data-muted={muted ? '' : undefined}>{initials}</span>
  );
}
