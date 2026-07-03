'use client'

export function EmptyState({ title, description, icon }: { title?: string; description?: string; icon?: string }) {
  return (
    <div style={{ textAlign: 'center', padding: 40 }}>
      <p style={{ color: 'var(--text-faint)', fontSize: 13 }}>{title || 'No data available'}</p>
      {description && <p style={{ color: 'var(--text-sub)', fontSize: 11 }}>{description}</p>}
    </div>
  )
}
