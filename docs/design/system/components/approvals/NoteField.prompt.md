NoteField is the optional note a manager adds when denying.

~~~jsx
<NoteField label="Note to Zara (optional)" helper="Zara will see this note. Up to 300 characters." value={note} onChange={setNote} />
~~~

- Always optional, and only on a denial. Approvals carry no note.
- Never a reason field on the employee's side.
