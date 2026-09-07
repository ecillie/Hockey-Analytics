import type { ReactNode, SVGProps } from 'react'

const paths: Record<string, ReactNode> = {
  search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,
  overview: <><path d="M4 13h6V4H4v9Zm10 7h6V4h-6v16ZM4 20h6v-3H4v3Z"/></>,
  players: <><circle cx="9" cy="8" r="3"/><path d="M3 20c0-4 2.5-7 6-7s6 3 6 7M16 5c2.5.2 4 1.7 4 4s-1.5 3.8-4 4M17 14c2.4.8 4 3 4 6"/></>,
  teams: <><path d="M4 20V8l8-4 8 4v12M8 20v-7h8v7M3 20h18"/></>,
  compare: <><path d="M8 5h12M16 2l4 3-4 3M16 19H4M8 16l-4 3 4 3"/></>,
  arrow: <path d="m9 18 6-6-6-6"/>,
  chevron: <path d="m8 10 4 4 4-4"/>,
}
export function Icon({ name, ...props }: { name: keyof typeof paths } & SVGProps<SVGSVGElement>) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name]}</svg>
}
