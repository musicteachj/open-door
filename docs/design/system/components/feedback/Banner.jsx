import React from 'react';
import { Icon } from '../core/Icon.jsx';

const ICON = { warning: 'triangle-alert', info: 'info' };

export function Banner({ message, tone = 'warning', onDismiss, dismissLabel = 'Dismiss for this session', className = '', ...rest }) {
  return (
    <div role="status" className={'od-banner ' + className} {...rest}>
      <Icon name={ICON[tone] || 'info'} size={18} className={'od-tone-' + tone} />
      <p className="od-banner__msg">{message}</p>
      {onDismiss && <button type="button" className="od-icon-btn" aria-label={dismissLabel} onClick={onDismiss}><Icon name="x" size={16} /></button>}
    </div>
  );
}
