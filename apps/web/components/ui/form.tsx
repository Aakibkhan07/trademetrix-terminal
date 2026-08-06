'use client'

import type { CSSProperties, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'

/** Label + control wrapper — mirrors the dominant `label` + `t-input`/`t-select` row patterns. */
export function Field({ label, children, labelClassName, labelStyle, style }: {
  label: ReactNode
  children: ReactNode
  labelClassName?: string
  labelStyle?: CSSProperties
  style?: CSSProperties
}) {
  return (
    <div style={style}>
      <label className={labelClassName || 't-label'} style={labelStyle}>{label}</label>
      {children}
    </div>
  )
}

/** Text/number input — emits `t-input` (+ optional `t-input-xs`). */
export function Input({ className, small, ...rest }: InputHTMLAttributes<HTMLInputElement> & { small?: boolean }) {
  return <input className={[small ? 't-input t-input-xs' : 't-input', className].filter(Boolean).join(' ') || undefined} {...rest} />
}

/** Select — emits `t-select`. */
export function Select({ className, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={className || 't-select'} {...rest} />
}
