import React from 'react';
import { Icon } from '../core/Icon.jsx';
import { ChoiceGroup } from '../timeoff/ChoiceGroup.jsx';
import { FormMessage } from '../timeoff/FormMessage.jsx';

const CASE_CATEGORIES = ['Harassment or discrimination', 'Workplace safety', 'Medical or accommodation', 'Pay concern', 'Something else, or not sure'];
const tel = (href, text, nowrap) => <a href={href} className="od-link" style={nowrap ? { whiteSpace: 'nowrap' } : undefined}>{text}</a>;

// The confidential-case form. Not a modal: it opens in place (the HR panel's band, or a card on My cases).
// state: 'form' | 'sending' | 'error' (send failed). The AI never submits this; only the person's own press of Send to HR does.
export function CaseForm({ id = 'case', headingLevel = 3, state = 'form', category = null, words = '', short = false, replyBy = 'Wednesday, October 28',
  errors = {}, onCategory, onWords, onSend, onClose, sendState, max = 4000 }) {
  const busy = state === 'sending';
  const n = words.length, atLimit = n >= max;
  const H = 'h' + headingLevel, H2 = 'h' + (headingLevel + 1);
  const count = atLimit ? max.toLocaleString('en-US') + ' of ' + max.toLocaleString('en-US') + ' characters. Shorten it to send.' : n.toLocaleString('en-US') + ' of ' + max.toLocaleString('en-US') + ' characters';
  return (
    <div className="od-case">
      <H id={id + '-h'} tabIndex={-1} className="od-case__title" data-case-h><Icon name="lock" />Open a confidential case</H>
      <div className="od-field">
        <ChoiceGroup id={id + '-cat'} label="What is this about?" disabled={busy} value={category} onChange={onCategory}
          options={CASE_CATEGORIES.map((c) => ({ value: c, label: c }))} />
        {errors.category && <p role="alert" id={id + '-ce'} className="od-field-error"><Icon name="circle-alert" size={16} />{errors.category}</p>}
      </div>
      <div className="od-field" style={{ gap: 6 }}>
        <label htmlFor={id + '-w'} className="od-case__label">Your words</label>
        <p id={id + '-wh'} className="od-case__hint">{short ? 'Add what happened, when, where, and who was involved, as much as you know.' : 'Say what happened, when, where, and who was involved, as much as you know.'}</p>
        <textarea id={id + '-w'} className="od-case__input" rows={6} maxLength={max} value={words} disabled={busy}
          aria-invalid={!!(errors.words || errors.limit)} aria-describedby={[id + '-wh', id + '-wc', errors.words && id + '-we'].filter(Boolean).join(' ')}
          onChange={(e) => onWords && onWords(e.target.value.slice(0, max))} />
        <div className="od-case__foot">
          {errors.words && <p role="alert" id={id + '-we'} className="od-field-error"><Icon name="circle-alert" size={16} />{errors.words}</p>}
          <span id={id + '-wc'} className="od-case__count" data-limit={atLimit} data-error={!!errors.limit} role={errors.limit ? 'alert' : undefined}>{count}</span>
        </div>
      </div>
      <div className="od-case__before">
        <H2 className="od-case__label" style={{ margin: 0 }}>Before you send</H2>
        <ul>
          <li>HR sees your name and the words below. Managers never see a case, including your own manager.</li>
          <li>Your case is stored encrypted.</li>
          <li>HR replies by {replyBy}, within 2 business days.</li>
          <li>Open Door’s AI writes HR a short summary of what you send, written to be neutral, with no recommendation. Anthropic, the company that runs Open Door’s AI, processes your words to write it. A person in HR reads your own words before deciding anything.</li>
          <li>If you or someone else is in danger, {tel('tel:911', 'call 911')}. You can {tel('tel:988', 'call or text 988')} to reach the 988 Suicide &amp; Crisis Lifeline, or call the Employee Assistance Program at {tel('tel:18005550137', '1-800-555-0137', true)}.</li>
        </ul>
      </div>
      {state === 'error' && <FormMessage tone="refusal">Your case wasn’t sent. Please try again.</FormMessage>}
      <div className="od-case__actions">
        <button type="button" className="od-btn od-btn--primary" data-case-send data-state={sendState} aria-disabled={busy || undefined} aria-busy={busy || undefined} onClick={busy ? undefined : onSend}>
          {busy && <Icon name="loader-circle" size={16} strokeWidth={2} className="od-spin" />}{busy ? 'Sending…' : state === 'error' ? 'Try again' : 'Send to HR'}
        </button>
        <button type="button" className="od-btn od-btn--secondary" disabled={busy} onClick={onClose}>Not now</button>
      </div>
    </div>
  );
}
