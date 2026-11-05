import React from 'react';

// The tour's last step: a centered, non-modal card over the console. No dimming, no celebration.
export function TourEndCard({ id = 'tour-end', persona = 'Dana', onKeepExploring, onChoose, headingRef, style }) {
  return (
    <div role="dialog" aria-modal="false" aria-labelledby={id + '-t'} className="od-tour-end" style={style}>
      <span aria-hidden="true" className="od-coach__step">Step 10 of 10</span>
      <h2 id={id + '-t'} ref={headingRef} tabIndex={-1}><span className="od-sr">Step 10 of 10: </span>That’s the tour</h2>
      <p>You’ve seen answers that change by state and always cite the handbook, a day off requested and approved on cards a person confirmed, private details kept private, a sensitive concern sent to HR in the person’s own words, and a record of everything the AI did.</p>
      <p className="od-tour-end__muted">This sandbox stays for 24 hours, so keep exploring.</p>
      <div className="od-tour-end__actions">
        <button type="button" className="od-btn od-btn--primary" onClick={onKeepExploring}>Keep exploring as {persona}</button>
        <button type="button" className="od-btn od-btn--secondary" onClick={onChoose}>Choose who to be</button>
      </div>
    </div>
  );
}
