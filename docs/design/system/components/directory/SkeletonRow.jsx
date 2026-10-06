import React from 'react';

const WIDTHS = [['46%', '62%', '50%', '58%'], ['58%', '48%', '40%', '66%'], ['40%', '70%', '56%', '52%'], ['52%', '56%', '44%', '60%']];

export function SkeletonRow({ variant = 0 }) {
  const w = WIDTHS[variant % WIDTHS.length];
  return (
    <div className="od-dir-cols od-skel-row" aria-hidden="true">
      <span className="od-dir-row__name"><span className="od-skel od-skel--avatar"></span><span className="od-skel" style={{ width: w[0] }}></span></span>
      <span className="od-skel" style={{ width: w[1] }}></span>
      <span className="od-skel" style={{ width: w[2] }}></span>
      <span className="od-skel" style={{ width: w[3] }}></span>
      <span></span>
    </div>
  );
}
