DecisionDialog confirms a manager's decision on one PTO request.

~~~jsx
<DecisionDialog kind="deny" person={{ name: 'Zara Bautista', first: 'Zara' }}
  facts="Monday, November 9 to Tuesday, November 10, 16 hours (2 days)." note={note} onNoteChange={setNote}
  phase={phase} onConfirm={decide} onBack={close} />
~~~

- One request at a time. No bulk decisions.
- After the engine answers: close, show the toast, move focus to the next waiting request's Approve, or to the "Waiting for you" heading when none are left.
- If the request changed (canceled, already decided), close and show the refusal on the card instead of the toast.
- Approve and Deny carry equal weight. The confirm is the standard primary button in both dialogs; never destructive, never red.
- No pronouns: Open Door has no pronoun data. Write "Zara will see it on the Time off page."
