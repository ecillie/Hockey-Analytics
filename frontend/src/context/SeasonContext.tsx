import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, type SeasonInfo } from '../api'

interface SeasonState { season: number; setSeason: (season: number) => void; info: SeasonInfo | null }
const SeasonContext = createContext<SeasonState | null>(null)

export function SeasonProvider({ children }: { children: ReactNode }) {
  const [info, setInfo] = useState<SeasonInfo | null>(null)
  const [season, setSeasonValue] = useState(2025)
  useEffect(() => {
    const controller = new AbortController()
    api.getSeasons(controller.signal).then((result) => { setInfo(result); setSeasonValue(result.currentSeason) }).catch(() => undefined)
    return () => controller.abort()
  }, [])
  const setSeason = (value: number) => { setSeasonValue(value); window.localStorage.setItem('tradevalue-season', String(value)) }
  const value = useMemo(() => ({ season, setSeason, info }), [season, info])
  return <SeasonContext.Provider value={value}>{children}</SeasonContext.Provider>
}

export function useSeason() {
  const context = useContext(SeasonContext)
  if (!context) throw new Error('useSeason must be used within SeasonProvider')
  return context
}
