import type { Contract, PlayerStats, PlayerSummary, SeasonHistoryRow, TeamSummary } from '../api/types'

export const mockTeams: TeamSummary[] = [
  ['ANA', 'Anaheim Ducks', 'Anaheim'], ['BOS', 'Boston Bruins', 'Boston'], ['BUF', 'Buffalo Sabres', 'Buffalo'],
  ['CAR', 'Carolina Hurricanes', 'Raleigh'], ['CBJ', 'Columbus Blue Jackets', 'Columbus'], ['CGY', 'Calgary Flames', 'Calgary'],
  ['CHI', 'Chicago Blackhawks', 'Chicago'], ['COL', 'Colorado Avalanche', 'Denver'], ['DAL', 'Dallas Stars', 'Dallas'],
  ['DET', 'Detroit Red Wings', 'Detroit'], ['EDM', 'Edmonton Oilers', 'Edmonton'], ['FLA', 'Florida Panthers', 'Sunrise'],
  ['LAK', 'Los Angeles Kings', 'Los Angeles'], ['MIN', 'Minnesota Wild', 'Saint Paul'], ['MTL', 'Montréal Canadiens', 'Montréal'],
  ['NJD', 'New Jersey Devils', 'Newark'], ['NSH', 'Nashville Predators', 'Nashville'], ['NYI', 'New York Islanders', 'Elmont'],
  ['NYR', 'New York Rangers', 'New York'], ['OTT', 'Ottawa Senators', 'Ottawa'], ['PHI', 'Philadelphia Flyers', 'Philadelphia'],
  ['PIT', 'Pittsburgh Penguins', 'Pittsburgh'], ['SEA', 'Seattle Kraken', 'Seattle'], ['SJS', 'San Jose Sharks', 'San Jose'],
  ['STL', 'St. Louis Blues', 'St. Louis'], ['TBL', 'Tampa Bay Lightning', 'Tampa'], ['TOR', 'Toronto Maple Leafs', 'Toronto'],
  ['UTA', 'Utah Mammoth', 'Salt Lake City'], ['VAN', 'Vancouver Canucks', 'Vancouver'], ['VGK', 'Vegas Golden Knights', 'Las Vegas'],
  ['WPG', 'Winnipeg Jets', 'Winnipeg'], ['WSH', 'Washington Capitals', 'Washington'],
].map(([abbreviation, name, city], index) => ({ id: index + 1, nhlTeamId: index + 1, abbreviation, name, city, active: true }))

const team = (abbr: string) => mockTeams.find((item) => item.abbreviation === abbr)!
type Seed = [string, string, string, PlayerSummary['primaryPosition'], number, number, number, number, number, number, number, PlayerSummary['rosterStatus']]

const seeds: Seed[] = [
  ['Connor', 'McDavid', 'EDM', 'C', 78, 44, 82, 126, 73.8, 2.91, 45.7, 'ACTIVE'],
  ['Nathan', 'MacKinnon', 'COL', 'C', 80, 39, 79, 118, 70.4, 2.75, 42.9, 'ACTIVE'],
  ['Leon', 'Draisaitl', 'EDM', 'C', 79, 52, 54, 106, 63.1, 2.63, 39.6, 'ACTIVE'],
  ['Nikita', 'Kucherov', 'TBL', 'RW', 77, 36, 74, 110, 65.7, 2.78, 40.8, 'ACTIVE'],
  ['Cale', 'Makar', 'COL', 'D', 79, 28, 66, 94, 62.2, 2.21, 37.4, 'ACTIVE'],
  ['Auston', 'Matthews', 'TOR', 'C', 76, 48, 39, 87, 57.5, 2.46, 34.1, 'ACTIVE'],
  ['Kirill', 'Kaprizov', 'MIN', 'LW', 71, 42, 55, 97, 60.4, 2.67, 35.8, 'ACTIVE'],
  ['Jack', 'Hughes', 'NJD', 'C', 74, 34, 58, 92, 54.9, 2.55, 32.2, 'ACTIVE'],
  ['Aleksander', 'Barkov', 'FLA', 'C', 75, 27, 59, 86, 55.2, 2.38, 33.5, 'ACTIVE'],
  ['Quinn', 'Hughes', 'VAN', 'D', 80, 19, 69, 88, 59.9, 2.16, 35.1, 'ACTIVE'],
  ['Adam', 'Fox', 'NYR', 'D', 77, 14, 56, 70, 51.4, 2.03, 30.7, 'ACTIVE'],
  ['David', 'Pastrnak', 'BOS', 'RW', 81, 43, 52, 95, 57.7, 2.43, 33.8, 'ACTIVE'],
  ['Mikko', 'Rantanen', 'DAL', 'RW', 80, 40, 59, 99, 58.2, 2.48, 34.4, 'ACTIVE'],
  ['Sebastian', 'Aho', 'CAR', 'C', 79, 33, 49, 82, 49.6, 2.23, 29.5, 'ACTIVE'],
  ['Kyle', 'Connor', 'WPG', 'LW', 80, 41, 48, 89, 50.1, 2.29, 30.3, 'ACTIVE'],
  ['Brady', 'Tkachuk', 'OTT', 'LW', 81, 36, 42, 78, 47.5, 2.12, 27.9, 'ACTIVE'],
  ['Matvei', 'Michkov', 'PHI', 'RW', 75, 29, 37, 66, 37.1, 1.92, 20.6, 'ACTIVE'],
  ['Macklin', 'Celebrini', 'SJS', 'C', 73, 31, 44, 75, 42.2, 2.14, 24.1, 'ACTIVE'],
  ['Alex', 'Ovechkin', 'WSH', 'LW', 74, 35, 31, 66, 34.7, 1.83, 18.4, 'ACTIVE'],
  ['Carey', 'Price', 'MTL', 'G', 0, 0, 0, 0, 0, 0, 0, 'LTIR'],
  ['Logan', 'Cooley', 'UTA', 'C', 78, 24, 36, 60, 33.8, 1.86, 18.9, 'ACTIVE'],
  ['Matthew', 'Savoie', 'BUF', 'C', 21, 5, 9, 14, 9.7, 1.45, 5.8, 'MINORS'],
]

const birthYear = [1997, 1995, 1995, 1993, 1998, 1997, 1997, 2001, 1995, 1999, 1998, 1996, 1996, 1997, 1996, 1999, 2004, 2006, 1985, 1987, 2004, 2004]
const capHits = [1250000000, 1260000000, 1400000000, 950000000, 900000000, 1325000000, 900000000, 800000000, 1000000000, 785000000, 950000000, 1125000000, 1200000000, 950000000, 714285700, 820833300, 95000000, 97500000, 950000000, 1050000000, 445000000, 88600000]

export const mockPlayers: PlayerSummary[] = seeds.map(([firstName, lastName, abbr, primaryPosition, gamesPlayed, goals, assists, points, gameScore, gameScorePer60, hockeyValue, rosterStatus], index) => ({
  id: index + 101,
  firstName,
  lastName,
  fullName: `${firstName} ${lastName}`,
  birthDate: `${birthYear[index]}-01-13`,
  age: 2026 - birthYear[index],
  primaryPosition,
  shootsCatches: index % 3 === 0 ? 'L' : 'R',
  nationality: index % 4 === 0 ? 'CAN' : index % 4 === 1 ? 'USA' : index % 4 === 2 ? 'SWE' : 'FIN',
  active: rosterStatus !== 'LTIR',
  rosterStatus,
  team: team(abbr),
  season: 2025,
  gamesPlayed,
  goals,
  assists,
  points,
  toiSeconds: gamesPlayed ? Math.round(gamesPlayed * (primaryPosition === 'D' ? 1430 : 1180)) : 0,
  gameScore,
  gameScorePer60,
  hockeyValue,
  projectedNextSeasonHockeyValue: hockeyValue ? Number((hockeyValue * (index > 17 ? 0.91 : 0.98)).toFixed(1)) : 0,
  capHitCents: capHits[index],
}))

export const mockPlayerStats: Record<number, PlayerStats> = Object.fromEntries(mockPlayers.map((p) => [p.id, {
  playerId: p.id,
  season: p.season,
  team: p.team,
  traditional: p.primaryPosition === 'G' ? null : {
    gamesPlayed: p.gamesPlayed, goals: p.goals, assists: p.assists, points: p.points, plusMinus: (p.id % 31) - 10,
    penaltyMinutes: p.id % 48, powerPlayGoals: Math.round((p.goals ?? 0) * .25), powerPlayPoints: Math.round((p.points ?? 0) * .3),
    shortHandedGoals: p.id % 3, shots: (p.goals ?? 0) * 6, shootingPercentage: p.goals ? .145 : 0,
  },
  advanced: p.primaryPosition === 'G' ? null : {
    situation: 'all', iceTimeSeconds: p.toiSeconds, shifts: (p.gamesPlayed ?? 0) * 24, gameScore: p.gameScore, gameScorePer60: p.gameScorePer60,
    individualExpectedGoals: (p.goals ?? 0) * .88, expectedGoalsPer60: (p.gameScorePer60 ?? 0) * .38, onIceExpectedGoalsPercentage: .5 + (p.id % 11) / 100,
    takeaways: 31 + p.id % 29, giveaways: 24 + p.id % 26, shotsBlocked: 14 + p.id % 38, penalties: p.id % 18, penaltiesDrawn: 8 + p.id % 20,
  },
  goalie: p.primaryPosition !== 'G' ? null : {
    gamesPlayed: 0, wins: 0, losses: 0, overtimeLosses: 0, shotsAgainst: 0, saves: 0, savePercentage: null, goalsAgainstAverage: null,
    shutouts: 0, timeOnIceSeconds: 0, expectedGoalsAgainst: null, goalsSavedAboveExpected: null,
  },
}]))

export const mockHistory: Record<number, SeasonHistoryRow[]> = Object.fromEntries(mockPlayers.map((p) => [p.id, [2022, 2023, 2024, 2025].map((season, i) => ({
  season, team: p.team, gamesPlayed: Math.max(0, (p.gamesPlayed ?? 0) - 5 + i), goals: Math.max(0, (p.goals ?? 0) - 6 + i * 2),
  assists: Math.max(0, (p.assists ?? 0) - 8 + i * 2), points: Math.max(0, (p.points ?? 0) - 14 + i * 4),
  gameScorePer60: Math.max(0, Number(((p.gameScorePer60 ?? 0) - .3 + i * .1).toFixed(2))), hockeyValue: Math.max(0, Number(((p.hockeyValue ?? 0) - 4.5 + i * 1.5).toFixed(1))),
}))]))

export const mockContracts: Record<number, Contract> = Object.fromEntries(mockPlayers.filter((p) => p.capHitCents).map((p) => [p.id, {
  id: p.id + 1000, playerId: p.id, signingTeam: p.team, signedOn: '2023-07-01', startSeason: 2024, endSeason: 2027,
  termYears: 4, contractType: 'STANDARD', expiryStatus: 'UFA', totalValueCents: (p.capHitCents ?? 0) * 4, averageValueCents: p.capHitCents,
  isEntryLevel: p.age !== null && p.age < 23,
  seasons: [2024, 2025, 2026, 2027].map((season) => ({ season, owningTeam: p.team, baseSalaryCents: p.capHitCents, signingBonusCents: 0,
    performanceBonusCents: null, totalCashCents: p.capHitCents, capHitCents: p.capHitCents ?? 0, capPercentage: (p.capHitCents ?? 0) / 9550000000,
    isSlide: false })),
}]))

export const mockSeasons = {
  currentSeason: 2025,
  availableSeasons: Array.from({ length: 18 }, (_, i) => {
    const startYear = 2008 + i
    return { startYear, endYear: startYear + 1, label: `${startYear}-${String(startYear + 1).slice(-2)}`, salaryCapCents: startYear === 2025 ? 9550000000 : null }
  }),
}
