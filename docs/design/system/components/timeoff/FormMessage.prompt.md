FormMessage explains a rule that applies to what's in the form.

~~~jsx
<FormMessage tone="warning">More than 3 days usually needs 2 weeks’ notice. You can still request it.</FormMessage>
<FormMessage tone="refusal">You already have time off on Wednesday, December 23.</FormMessage>
~~~

- One or two sentences, with the numbers. No blame.
- Warnings never block. Refusals always disable submit.
