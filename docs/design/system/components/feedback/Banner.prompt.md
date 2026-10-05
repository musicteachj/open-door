Banner flags something about the whole session, such as the sandbox about to reset.

~~~jsx
{minutesLeft <= 180 && !dismissed && (
  <Banner message="This sandbox resets in 2 h 50 min. Everything you've done here will be cleared." onDismiss={() => setDismissed(true)} />
)}
~~~

- Show the expiry banner when 3 hours or less remain; remember dismissal in sessionStorage.
- Hours and minutes under 3 hours ("2 h 50 min"), hours only above.
