Composer is the assistant's ask box, the center of the home screen; use it wherever someone asks Open Door a question.

~~~jsx
<Composer value={q} onChange={setQ} onSubmit={send} />
<Composer value={q} onChange={setQ} onSubmit={send} error="Something went wrong sending that." />
~~~

- The disclosure is part of the component and is never removed.
- Placeholder names the topics the assistant covers.
- Built on a shadcn Textarea and Button, restyled. Text fields elsewhere use the same input-border tokens.
