InlineError reports a failure right under the control that caused it, with a way to try again.

~~~jsx
<InlineError message="Something went wrong sending that." onRetry={resend} />
~~~

- Say what happened in plain words. Don't blame the user, use "oops", or add exclamation points.
- Keep the user's input in place so Retry resends it.
- Icon plus text, so color is never the only signal.
