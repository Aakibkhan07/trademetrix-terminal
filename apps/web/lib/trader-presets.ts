'use client'

/**
 * Saved trading presets (localStorage only — no backend).
 *
 * A preset captures the trader's pick state: index, moneyness, CE/PE, lots, and
 * order type. Selecting a preset restores the exec workspace; saving captures the
 * current form. Presets survive reloads and are per-browser.
 */

import type { IndexKey, Moneyness } from '@/lib/options-contracts'

export interface TraderPreset {
  id: string
  name: string
  index: IndexKey
  moneyness: Moneyness
  customStrike: number | null
  optionType: 'CE' | 'PE'
  lots: number
  orderType: 'MARKET' | 'LIMIT'
  createdAt: number
}

const KEY = 'tm_trader_presets_v1'
const MAX_PRESETS = 12

export function loadPresets(): TraderPreset[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as TraderPreset[]
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function savePreset(input: Omit<TraderPreset, 'id' | 'createdAt'>): TraderPreset[] {
  const preset: TraderPreset = { ...input, id: Math.random().toString(36).slice(2, 10), createdAt: Date.now() }
  const next = [preset, ...loadPresets()].slice(0, MAX_PRESETS)
  persist(next)
  return next
}

export function deletePreset(id: string): TraderPreset[] {
  const next = loadPresets().filter(p => p.id !== id)
  persist(next)
  return next
}

function persist(list: TraderPreset[]) {
  if (typeof window === 'undefined') return
  try { window.localStorage.setItem(KEY, JSON.stringify(list)) } catch { /* ignore */ }
}