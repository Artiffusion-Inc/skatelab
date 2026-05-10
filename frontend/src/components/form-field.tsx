import type { ComponentProps } from "react"

const inputClasses =
  "w-full rounded-md border border-hairline bg-background px-3 py-2.5 text-sm transition-colors duration-200 placeholder:text-ink-faint focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/20 disabled:opacity-50"

export function FormField({
  label,
  id,
  ...props
}: { label: string; id: string } & ComponentProps<"input">) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="sh-caption font-medium text-ink">
        {label}
      </label>
      <input id={id} {...props} className={`${inputClasses} ${props.className ?? ""}`} />
    </div>
  )
}

export function FormSelect({
  label,
  id,
  children,
  ...props
}: { label: string; id: string; children: React.ReactNode } & ComponentProps<"select">) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="sh-caption font-medium text-ink">
        {label}
      </label>
      <select id={id} {...props} className={`${inputClasses} ${props.className ?? ""}`}>
        {children}
      </select>
    </div>
  )
}

export function FormTextarea({
  label,
  id,
  ...props
}: { label: string; id: string } & ComponentProps<"textarea">) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="sh-caption font-medium text-ink">
        {label}
      </label>
      <textarea id={id} {...props} className={`${inputClasses} ${props.className ?? ""}`} />
    </div>
  )
}