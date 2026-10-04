SkeletonRow stands in for a directory row while data loads.

~~~jsx
{[0, 1, 2, 3, 4, 5, 6, 7].map((i) => <SkeletonRow key={i} variant={i} />)}
~~~

- Show eight rows, keep the column header and toolbar, and replace the count with a short bar.
- No shimmer animation; the system has no decorative motion.
