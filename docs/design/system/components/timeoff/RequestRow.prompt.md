RequestRow lists one request with its status.

~~~jsx
<RequestGroup title="Upcoming">
  <RequestRow dates="Wednesday, December 23" amount="8 hours (1 day)" status="approved" decidedBy="Marcus Bell" canCancel onCancel={confirm} />
</RequestGroup>
~~~

- Cancel always goes through one confirm step: "Cancel your time off on …? 8 hours go back to your balance." with "Cancel request" and "Keep it".
- Cancel's accessible name names the request: "Cancel PTO on Wednesday, December 23".
