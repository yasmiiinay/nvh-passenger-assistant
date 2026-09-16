# Nordhaven International Airport (NVH) — Fictional Airport Specification v1

Status: **frozen** after the foundation stage. Change only on a structural error, never for convenience.
Everything in this document is **synthetic**. The airport, its code, all names, hours and
layout are invented for AI7016. No real airport's data was copied. The IATA-style code
"NVH" is a fiction and has **not** been checked against the IATA registry
(*design assumption*, Evidence Pack §F).

## 1. Identity and setting

| Field | Value |
|---|---|
| Name | Nordhaven International Airport |
| Code | NVH (fictional, IATA-style) |
| Setting | Mid-size coastal city "Nordhaven", northern Europe (fictional) |
| Scale | ~9 M passengers/year (flavour only; never used by the system) |
| Terminals | 2 |
| Piers / gates | A (A1–A12) and B (B1–B18) in Terminal 1; C (C1–C10) in Terminal 2 |

**Gate naming convention** — letter pier + number within pier (`A7`, `B12`, `C3`).
This is a *design assumption* modelled on common practice; no authoritative naming
standard exists (Evidence Pack §F.2). Consequence for the system: the gate-identifier
pattern is `^[ABC][0-9]{1,2}$` with per-pier ranges, so `B21` and `D4` are *well-formed
but non-existent* — exactly the cases the abstain/clarify path must handle.

## 2. Terminal 1 (main terminal)

| Level | Name | Contents |
|---|---|---|
| 0 | Arrivals | Baggage reclaim (belts 1–6), lost property office, arrivals information desk, taxi rank, landside café, restrooms, PRM assistance point (main entrance) |
| 1 | Departures | Check-in Hall (desks 101–160), departures information desk, security North and security South, PRM assistance point (check-in hall), restrooms |
| 2 | Airside | Piers A and B, Aurora Lounge (near B gates), Skyline Restaurant, airside restrooms |

Sub-areas ("zones") used by the KB: `Arrivals Hall`, `Check-in Hall`, `Pier A`, `Pier B`,
`Airside Plaza` (the area between the piers, where the lounge and restaurant sit).

## 3. Terminal 2 (compact terminal)

| Level | Name | Contents |
|---|---|---|
| 0 | Arrivals | Baggage reclaim (belts 7–9), restrooms |
| 1 | Departures | Check-in desks 201–230, single security checkpoint, information desk, Pier C, Pier C Café, restrooms with accessible toilet, PRM assistance point |

Terminal 2 deliberately has **no lounge and no lost-property office** — those services
exist only in Terminal 1. This asymmetry is intentional: it creates realistic queries
("is there a lounge in Terminal 2?") whose correct answer is a grounded *no* with a
pointer, which the response templates must be able to express.

## 4. Ground transport (landside, between the terminals)

KB note: every record has a `terminal` (where it is). The services in this
section, plus the flight boards and the first-aid room, also carry
`serves_terminals: ["Terminal 1", "Terminal 2"]`, because a Terminal 2
passenger uses them; the grounded-negative and terminal-narrowing rules read
that field, not `terminal`. Records without it serve only their own terminal
(the lounge and lost-property asymmetries above rely on this).

- **Nordhaven Airport rail station** — below Terminal 1; PRM assistance point at the
  station entrance (per Regulation 1107/2006 recital 5, designated points belong at
  rail stations serving the airport — Evidence Pack §A8).
- **Bus terminal** — outside Terminal 1 Arrivals, ground level.
- **Taxi rank** — outside Terminal 1 Arrivals. (Terminal 2 passengers are directed to
  the shuttle or the T1 rank; another intentional asymmetry.)
- **Car park P1** — multi-storey, opposite Terminal 1, footbridge to Departures level.
- **Terminal shuttle** — free bus, T1 ↔ T2, every 10 minutes 04:00–01:00
  (synthetic timetable; `volatility: medium`).

## 5. Assistance and emergency path

Modelled on Regulation (EC) No 1107/2006 Art. 5 (designated points) and Annex I
(basic information in accessible formats) — see Evidence Pack §A8. Designated PRM
assistance points:

1. Terminal 1 main entrance (Arrivals level)
2. Terminal 1 Check-in Hall
3. Terminal 2 entrance
4. Rail station entrance

Assistance/emergency contact path (all synthetic): any information desk → airport
assistance line "+00 000 0000" → first-aid room (Terminal 1, Departures level, beside
security North). **Flight status, gate changes and delays are never answered from the
KB**; the `flight_information` record exists only to carry the redirect to the official
source (departure boards / the airline).

## 6. What the specification deliberately excludes

No airlines (the `airline` entity type exists in the vocabulary but has an empty
gazetteer in v1), no shops beyond food, no smoking areas, no pharmacy, no hotel.
Every exclusion creates an honest out-of-scope query for evaluation rather than a
KB record invented to avoid saying "I don't know".
