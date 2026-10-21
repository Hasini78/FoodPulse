type SourceNoteProps = {
  dataset: string
  unit: string
  sample?: boolean
}

export function SourceNote({ dataset, unit, sample = false }: SourceNoteProps) {
  return (
    <p className="text-[11px] leading-4 text-ink-3">
      Source: {dataset}. Unit of analysis: {unit}.
      {sample ? ' Sample or synthetic records, not live public data.' : ''}
    </p>
  )
}

export function MetricGlossary({ items }: { items: ReadonlyArray<{ term: string; meaning: string }> }) {
  return (
    <dl className="grid gap-3 sm:grid-cols-3">
      {items.map((item) => (
        <div key={item.term} className="rounded-xl bg-canvas px-4 py-3">
          <dt className="text-xs font-semibold text-ink">{item.term}</dt>
          <dd className="mt-1 text-xs leading-5 text-ink-3">{item.meaning}</dd>
        </div>
      ))}
    </dl>
  )
}
