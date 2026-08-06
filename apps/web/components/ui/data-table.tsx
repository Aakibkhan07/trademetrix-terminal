'use client'

import type { CSSProperties, ReactNode, TdHTMLAttributes, ThHTMLAttributes } from 'react'

/** Table wrapper — emits `t-table` (design system) with optional className/style overrides. */
export function DataTable({ className, style, children }: {
  className?: string
  style?: CSSProperties
  children: ReactNode
}) {
  return <table className={className || 't-table'} style={style}>{children}</table>
}

/** Table head cell. */
export function Th({ style, ...rest }: ThHTMLAttributes<HTMLTableCellElement>) {
  return <th style={style} {...rest} />
}

/** Table body cell. */
export function Td({ style, ...rest }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td style={style} {...rest} />
}
