ApprovalCard shows one PTO request waiting for a manager's decision.

~~~jsx
<ul className="od-approval-list">
  <ApprovalCard person={{ name: 'Zara Bautista', title: 'Department Lead, Apparel', initials: 'ZB' }}
    dates="Monday, November 9 to Tuesday, November 10" shortDates="November 9 to 10" amount="16 hours (2 days)"
    availableAfter="62 hours (7.75 days) available after this" sent="Sent October 17"
    coverage={['Also off: Vikram Morales, Tuesday, November 10 · PTO']} onApprove={open('approve')} onDeny={open('deny')} />
</ul>
~~~

- Only PTO appears here. Sick time is recorded, never decided.
- Coverage is context. Never color it, rank it, or add advice. No "Approve all".
- Approve and Deny are both secondary, same size, Approve first. Neither is filled.
- Approve and Deny open DecisionDialog; nothing is decided from the card itself.
- Oldest first.
