# CaseQueueTable

HR's queue at /cases. Directory-table density (64 px rows), rows are links to the case detail.

~~~jsx
<CaseQueueTable rows={[{ href: '/cases/c-1042', initials: 'PR', name: 'Priya Raman', title: 'Visual Merchandiser', location: 'Oakland store', category: 'Harassment or discrimination', sent: 'Mon, Oct 26', reply: 'Reply due Wed, Oct 28', status: 'case-new' }]} />
~~~

- Columns: Person (avatar, name, title · location), Category, Sent, Reply, Status.
- Never show any part of a case's words or summary. No severity, priority, risk, or score; the only order is new by reply date, then the rest oldest first.
- Overdue replies and the crisis fact are plain facts in neutral type: no red, no warning color, no icon in a warning hue.
- Filter above it: a SegmentedControl-style radiogroup, Open (default), New, In review, Closed, All.
- Phone: stacked rows (person, category, then reply line and badge).
