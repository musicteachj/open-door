import React from 'react';
import { Icon } from '../core/Icon.jsx';

export function FormMessage({ tone = 'warning', children }) {
  const refusal = tone === 'refusal';
  return (
    <div role={refusal ? 'alert' : 'status'} className={'od-msg od-msg--' + tone}>
      <Icon name={refusal ? 'circle-alert' : 'triangle-alert'} size={16} />
      <p>{children}</p>
    </div>
  );
}
