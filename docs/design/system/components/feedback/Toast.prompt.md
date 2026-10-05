Toast confirms something that just happened without interrupting.

~~~jsx
<div className="od-toast-region">
  {toast && <Toast message="Now viewing as Marcus Bell." onDismiss={() => setToast(null)} />}
</div>
~~~

- One sentence, ending with a period. No exclamation points.
- Errors go inline next to what failed (InlineError), not in a toast.
