import type { ReactNode } from 'react'

type Column = {
  key: string
  header: string
  render: (row: Record<string, unknown>) => ReactNode
  align?: 'left' | 'right'
}

type DataTableProps = {
  columns: Column[]
  rows: Array<Record<string, unknown>>
  caption?: string
}

export function DataTable({ columns, rows, caption }: DataTableProps) {
  return (
    <div className="-mx-1 max-h-[28rem] overflow-auto rounded-xl border border-line">
      <table className="min-w-full text-left text-sm">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead className="sticky top-0 z-10 bg-canvas text-xs font-semibold text-ink-3">
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col" className={['px-4 py-3 whitespace-nowrap', column.align === 'right' ? 'text-right' : ''].join(' ')}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((row, index) => (
            <tr key={index} className="transition-colors hover:bg-brand-soft/40">
              {columns.map((column) => (
                <td key={column.key} className={['px-4 py-3 align-top text-ink-2', column.align === 'right' ? 'text-right tabular-nums' : ''].join(' ')}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
