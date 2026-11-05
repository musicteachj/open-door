# ConsoleTile

~~~jsx
<ConsoleTile title="Time to first token" pre="Median" figure="1.6 s" lines={['95th percentile 2.2 s', 'Target 3 s']} foot="9 turns · Small sample" />
<ConsoleTile title="Safety check time" pre="95th percentile" figure="980 ms" lines={['Target 800 ms']} foot="9 turns · Small sample" />
<ConsoleTile title="Cards confirmed by a person" rows={[['Time-off requests', '1'], ['Decisions', '1'], ['Cancellations', '0']]} foot="From the audit log" />
<ConsoleTile title="Said the handbook doesn't cover it" figure="2" lines={['of 31 turns']} closest={['4.1 Paid time off (2)', '5.2 Parental leave (1)']} />
<ConsoleTile title="Cost per answered question" state="empty" spend="Sandbox spend $0.00 of $1.00 cap" />
~~~

- Every tile states its sample size. Under 20 turns the foot also says "Small sample".
- A figure above its target looks exactly like one below it: same ink, no icon, no tint. The target line states it.
- Grid: `.od-tiles` (auto-fill, 220 px minimum), four across at 1080 px, two beside a docked panel, one on phones.
- shadcn: Card with CardHeader/CardContent/CardFooter.
