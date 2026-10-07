import React from 'react';
import { Icon } from '../core/Icon.jsx';

export function AppliesMarker({ applies, className = '' }) {
  return applies
    ? <span className={'od-marker od-marker--yes ' + className}><Icon name="check" size={14} strokeWidth={2} />Applies to you</span>
    : <span className={'od-marker od-marker--no ' + className}><Icon name="minus" size={14} strokeWidth={2} />Doesn't apply to you</span>;
}
