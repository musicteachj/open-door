import React from 'react';
import { Icon } from '../core/Icon.jsx';

// The quiet result after a case is sent, and the five-waiting limit. role="status"; focus moves here.
// No apricot, no success check: a case is not a celebration.
export function CaseSent({ variant = 'sent', replyBy = 'Wednesday, October 28', showLink = true, href = '/my-cases' }) {
  if (variant === 'limit') {
    return <div role="status" className="od-case-sent"><Icon name="lock" size={20} /><div className="od-case-sent__body"><p>You have 5 cases waiting for HR. To add to one, contact the HR team directly.</p></div></div>;
  }
  return (
    <div role="status" tabIndex={-1} className="od-case-sent" data-case-sent>
      <Icon name="lock" size={20} />
      <div className="od-case-sent__body">
        <p>{'Sent to HR. HR replies by ' + replyBy + '.' + (showLink ? ' You can see its status in My cases.' : '')}</p>
        {showLink && <a href={href} className="od-link" style={{ alignSelf: 'flex-start' }}>View in My cases</a>}
      </div>
    </div>
  );
}
