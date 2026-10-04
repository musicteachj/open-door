DetailList groups profile fields under a heading.

~~~jsx
<DetailList title="Private details" icon="lock" note="Only Leo and HR can see these."
  auditNote="Viewing private details is recorded in the audit log.">
  <DetailRow label="Phone" value="(510) 555-0175" />
</DetailList>
~~~

- Every read of private details is audited, so pass auditNote whenever values are visible.
- Viewer is the person: note "Only you and HR can see these." plus the audit note.
- Viewer is HR: note "Only Leo and HR can see these." plus the audit note.
- Anyone else: no note; every row is locked.
