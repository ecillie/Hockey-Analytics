import { afterEach, describe, expect, it, vi } from 'vitest'
import { API_GET_PATHS } from './contract'
import { httpApi } from './httpService'

function contractPath(url: string) {
  return new URL(url).pathname
    .replace(/^\/api\/players\/\d+/, '/api/players/{player_id}')
    .replace(/^\/api\/teams\/\d+/, '/api/teams/{team_id}')
}

describe('HTTP API contract', () => {
  afterEach(() => vi.restoreAllMocks())

  it('maps every FastAPI endpoint and serializes representative query parameters', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      const body = url.includes('/contract')
        ? null
        : url.includes('/compare')
          ? { season: 2025, players: [] }
          : url.includes('/players')
            ? []
            : {}
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    })
    const signal = new AbortController().signal

    await httpApi.getHealth(signal)
    await httpApi.getSeasons(signal)
    await httpApi.getOverview(2025, signal)
    await httpApi.getPlayers(undefined, signal)
    await httpApi.getPlayers({ team: 'EDM' }, signal)
    await httpApi.getPlayer(101, signal)
    await httpApi.getPlayerStats(101, 2025, signal)
    await httpApi.getPlayerSeasons(101, signal)
    await httpApi.getPlayerValue(101, 2025, signal)
    await httpApi.getPlayerValueHistory(101, signal)
    await httpApi.getHockeyValueLeaders({ season: 2025, limit: 3 }, signal)
    await httpApi.getPlayerContract(101, signal)
    await httpApi.getTeams(signal)
    await httpApi.getTeam(11, signal)
    await httpApi.getTeamRoster(11, { season: 2025, status: 'ACTIVE' }, signal)
    await httpApi.getTeamContracts(11, 2025, signal)
    await httpApi.getTeamCap(11, 2025, signal)
    await httpApi.search('mcdavid', undefined, undefined, signal)
    await httpApi.search('oilers', ['team'], 2, signal)
    await httpApi.comparePlayers([101, 102], 2025, signal)

    const urls = fetchMock.mock.calls.map(([input]) => String(input))
    const calledPaths = urls.map(contractPath)
    expect([...new Set(calledPaths)].sort()).toEqual([...API_GET_PATHS].sort())
    expect(urls).toEqual(expect.arrayContaining([
      'http://localhost:8000/api/health',
      'http://localhost:8000/api/players?team=EDM',
      'http://localhost:8000/api/players/101/stats?season=2025',
      'http://localhost:8000/api/teams/11/roster?season=2025&status=ACTIVE',
      'http://localhost:8000/api/search?q=mcdavid&types=player%2Cteam&limit=8',
      'http://localhost:8000/api/players/compare?ids=101%2C102&season=2025',
    ]))
    expect(fetchMock).toHaveBeenCalledTimes(20)
  })
})
