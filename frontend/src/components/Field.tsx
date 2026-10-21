import type { ReactNode } from 'react'

const control =
  'mt-1 block w-full min-w-0 rounded-xl border border-line bg-card px-3 py-2 text-sm text-ink shadow-sm transition-colors hover:border-ink-3/40 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20 disabled:cursor-not-allowed disabled:bg-canvas disabled:text-ink-3'

type FieldProps = { label: string; children: ReactNode }

export function Field({ label, children }: FieldProps) {
  return (
    <label className="block min-w-0 text-xs font-semibold text-ink-2">
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
  disabled?: boolean
}

export function SelectField({ label, value, onChange, options, disabled }: SelectFieldProps) {
  return (
    <Field label={label}>
      <select className={control} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </Field>
  )
}

type TextFieldProps = { label: string; value: string; onChange: (value: string) => void; placeholder?: string; disabled?: boolean }

export function TextField({ label, value, onChange, placeholder, disabled }: TextFieldProps) {
  return (
    <Field label={label}>
      <input className={control} type="search" value={value} placeholder={placeholder} disabled={disabled} onChange={(event) => onChange(event.target.value)} />
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
