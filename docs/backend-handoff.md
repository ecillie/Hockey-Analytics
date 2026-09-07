# Backend API Handoff

Implement the HTTP layer exactly as specified in [api-contract.md](./api-contract.md). P0 provides seasons, core player/team navigation, statistics, and rosters. P1 adds the product-defining Hockey Value, contracts, cap, global search, and efficient overview aggregate. P2 is the comparison aggregate; the frontend can be adapted temporarily to compose P0/P1 calls if necessary.

The most important backend constraints are server-side filtering/sorting/pagination; `TOTAL` season records for traded players; nullable values preserved as null; integer cents; ratio decimals; joined table/roster payloads; consistent errors; and backend ownership of model and salary-cap calculations. Once implemented, the frontend cutover is only `VITE_USE_MOCK_API=false` plus `VITE_API_BASE_URL`.
