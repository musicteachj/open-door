import React from 'react';
import { Icon } from '../core/Icon.jsx';

export function SandboxIndicator({ hours = 21, label, className = '' }) {
  return (
    <span className={'od-sandbox ' + className}>
      <Icon name="clock" size={13} />
      {label || 'Sandbox resets in ' + hours + ' h'}
    </span>
  );
}
