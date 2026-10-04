import React from 'react';
import { Icon } from '../core/Icon.jsx';

export function DetailRow({ label, value, locked = false, reason, children }) {
  return (
    <div className="od-detail">
      <dt className="od-detail__label">{label}</dt>
      <dd className="od-detail__value">
        {locked
          ? <span className="od-detail__locked"><Icon name="lock" size={14} />{reason}<span className="od-sr-only">. Value hidden.</span></span>
          : (children || value)}
      </dd>
    </div>
  );
}
