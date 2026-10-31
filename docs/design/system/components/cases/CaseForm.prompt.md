# CaseForm

The confidential-case form. A person opens it themselves from the HR panel ("Open a confidential case") or from My cases. The AI never opens or submits a case and never says it will.

~~~jsx
<div className="od-case-band">
  <CaseForm id="c1" headingLevel={3} words="My manager keeps making comments about my age." category={cat} onCategory={setCat} onWords={setWords} onSend={send} onClose={close} />
</div>
~~~

- Wrap it in `.od-case-band` inside the HR panel (below the contacts, replacing the button) or `.od-case-card` on My cases. Quiet aubergine wash and a lock; never warning colors.
- Fields: category (ChoiceGroup, nothing preselected), "Your words" with hint above and counter below, then the five "Before you send" lines verbatim.
- Errors use `.od-field-error` with role="alert"; on Send, focus the first invalid field.
- Validation: no category; empty words; anything that looks like an SSN or card number; 4,000 characters.
- Buttons: "Send to HR" (primary), "Not now" (secondary). Sending: spinner and "Sending…", fields disabled.
- Opening moves focus to the heading; "Not now" returns it to the button that opened the form.
