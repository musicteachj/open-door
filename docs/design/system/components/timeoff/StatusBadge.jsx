import React from 'react';
import { Icon } from '../core/Icon.jsx';

const STATUS = {
  waiting: ['Waiting for approval', 'clock'],
  approved: ['Approved', 'circle-check'],
  denied: ['Denied', 'circle-x'],
  recorded: ['Recorded', 'clipboard-check'],
  canceled: ['Canceled', 'ban'],
  'case-sent': ['Sent to HR', 'clock'],
  'case-reviewing': ['HR is reviewing', 'file-search'],
  'case-finished': ['HR has finished its review', 'circle-check'],
  'case-new': ['New', 'dot'],
  'case-in-review': ['In review', 'file-search'],
  'case-closed': ['Closed', 'circle-check']
};

export function StatusBadge({ status = 'waiting', className = '' }) {
  const [label, icon] = STATUS[status] || STATUS.waiting;
  return (
    <span className={'od-badge od-badge--' + status + ' ' + className}>
      {icon === 'dot' ? <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true" style={{ flex: 'none' }}><circle cx="12" cy="12" r="5" fill="var(--marker)" /></svg> : <Icon name={icon} size={14} strokeWidth={2} />}
      {label}
    </span>
  );
}
