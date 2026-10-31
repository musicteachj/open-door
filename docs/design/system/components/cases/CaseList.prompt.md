# CaseList

My cases rows: category, sent date, a case status badge, and a date line. Newest first.

~~~jsx
<CaseList cases={[{ category: 'Harassment or discrimination', sent: 'Sent Mon, Oct 26', status: 'case-sent', line: 'HR replies by Wed, Oct 28' }]} />
~~~

- Rows are not links, and no row shows the person's words.
- Statuses (StatusBadge): case-sent "Sent to HR", case-reviewing "HR is reviewing", case-finished "HR has finished its review".
- Empty: `.od-case-empty` with "You haven't sent HR a case." and a primary "Open a confidential case".
- Phone: the date line moves under the category.
