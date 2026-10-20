import type { ReactNode } from 'react'

const control =
  'mt-1 block w-full min-w-[9rem] rounded-xl border border-line bg-card px-3 py-2 text-sm text-ink shadow-sm transition-colors hover:border-ink-3/40 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20'

type FieldProps = { label: string; children: ReactNode }

export function Field({ label, children }: FieldProps) {
  return (
    <label className="block text-xs font-semibold text-ink-2">
      {label}
      {children}
    </label>
  )
}

type Option = { value: string; label: string }

type SelectFieldProps = {
  label: string
  value: string
  onChange: (value: string) => void
  options: Option[]
}

export function SelectField({ label, value, onChange, options }: SelectFieldProps) {
  return (
    <Field label={label}>
      <select className={control} value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </Field>
  )
}

type DateFieldProps = { label: string; value: string; onChange: (value: string) => void }

export function DateField({ label, value, onChange }: DateFieldProps) {
  return (
    <Field label={label}>
      <input className={control} type="date" value={value} onChange={(event) => onChange(event.target.value)} />
    </Field>
  )
}
