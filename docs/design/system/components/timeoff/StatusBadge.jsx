import React from 'react';
import { Icon } from '../core/Icon.jsx';

const STATUS = {
  waiting: ['Waiting for approval', 'clock'],
  approved: ['Approved', 'circle-check'],
  denied: ['Denied', 'circle-x'],
  recorded: ['Recorded', 'clipboard-check'],
  canceled: ['Canceled', 'ban']
};

export function StatusBadge({ status = 'waiting', className = '' }) {
  const [label, icon] = STATUS[status] || STATUS.waiting;
  return (
    <span className={'od-badge od-badge--' + status + ' ' + className}>
      <Icon name={icon} size={14} strokeWidth={2} />
      {label}
    </span>
  );
}
