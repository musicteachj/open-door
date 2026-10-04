import React from 'react';
import { Icon } from '../core/Icon.jsx';
import { Button } from '../core/Button.jsx';

export function InlineError({ message = 'Something went wrong sending that.', onRetry, retryLabel = 'Retry', className = '' }) {
  return (
    <div role="alert" className={'od-inline-error ' + className}>
      <p className="od-inline-error__msg"><Icon name="circle-alert" size={16} />{message}</p>
      {onRetry && <Button variant="secondary" size="sm" icon="rotate-ccw" onClick={onRetry}>{retryLabel}</Button>}
    </div>
  );
}
