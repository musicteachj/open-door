/** An empty table cell: a dash for the eye, and `hidden` (default "None") for a screen reader. */
function EmptyCell({ hidden = 'None' }: { hidden?: string }) {
  return (
    <>
      <span aria-hidden="true" className="text-ink-muted">
        –
      </span>
      <span className="sr-only">{hidden}</span>
    </>
  )
}

export { EmptyCell }
