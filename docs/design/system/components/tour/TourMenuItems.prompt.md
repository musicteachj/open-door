# TourMenuItems and TourStartDialog

~~~jsx
<PersonaMenu personas={P} currentId="marcus" extra={<TourMenuItems onTake={() => setAsk(true)} />} />
<PersonaMenu personas={P} currentId="marcus" extra={<TourMenuItems step={5} onResume={resume} onRestart={restart} />} />
{ask && <TourStartDialog onStart={start} onCancel={() => setAsk(false)} />}
~~~

- Sits below the four personas and their note, above Sign out, between separators.
- Idle: "Take the tour" (circle-play). It opens the dialog; the tour never starts from one click inside the app because it replaces the sandbox view.
- In progress: "Resume the tour" with "Step 5 of 10" under it, returning to that step as its persona, and "Start the tour over".
- Dialog: 480 px alertdialog on the standard scrim, "Start the tour?", Cancel focused first, "Start the tour" primary. Escape cancels and returns focus to the menu item.
- On the landing, the tour starts from "Take the 2-minute tour" with no dialog: the button shows a spinner and "Starting the tour…" and the persona cards are disabled.
