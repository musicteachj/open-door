import React from 'react';
import { Icon } from '../core/Icon.jsx';

const ICON = { success: 'circle-check', info: 'info' };

export function Toast({ message, tone = 'success', duration = 6000, onDismiss, className = '' }) {
  React.useEffect(() => {
    if (!duration || !onDismiss) return undefined;
    const t = setTimeout(onDismiss, duration);
    return () => clearTimeout(t);
  }, [duration, onDismiss, message]);
  return (
    <div role="status" className={'od-toast ' + className}>
      <Icon name={ICON[tone] || 'info'} size={18} className={'od-tone-' + tone} />
      <p className="od-toast__msg">{message}</p>
      {onDismiss && <button type="button" className="od-icon-btn" aria-label="Dismiss" onClick={onDismiss}><Icon name="x" size={16} /></button>}
    </div>
  );
}
