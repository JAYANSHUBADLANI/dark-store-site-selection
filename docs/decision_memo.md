# Decision memo: where should the next 20 dark stores go in Bengaluru

**To:** whoever is deciding the Bengaluru expansion
**From:** the analysis in this repository
**Date:** August 2026

---

## The short version

**Do not spend the next month choosing 20 locations. The location choice does
not change what those 20 stores will deliver.**

At 20 stores, throughput is the binding constraint, not reach. Every store fills
to capacity regardless of where it sits, so any 20 sites with enough demand
nearby produce the same served volume. The spatial optimisation in this
repository, which I built to answer the question as asked, returns an answer
that is correct and irrelevant.

The question worth answering is **how many stores**, and that one has an
arithmetic answer.

---

## What was asked, and what the model said

The brief: place 20 dark stores to maximise the demand inside a 10 minute
delivery promise.

The covering model answers it. Solved exactly, 20 optimally placed stores put
**93.69% of modelled demand** inside the promise, and proves optimality in 1.1
seconds.

That number is real and it is misleading, because "inside the promise" means a
rider could get there in time. It says nothing about whether the store can
actually fulfil the order.

## What throughput does to that answer

A dark store has a ceiling. Using Blinkit's Q4 FY26 disclosure as an anchor,
273.9 million orders across 2,243 stores, roughly **40,700 orders per store per
month**:

| | |
|---|---:|
| Modelled Bengaluru demand | 5,547,356 orders per month |
| Coverage the model reports for 20 stores | 93.69% |
| Demand 20 stores can physically serve | **14.67%** |
| Capacity utilisation | **1.000** |

Utilisation of exactly 1.000 is the finding. Every store is full. Moving them
around cannot help, because nothing is idle. Confirmed across a sweep from
20,000 to 80,000 orders per store: served demand equals the capacity ceiling at
every level.

**Two solutions sharing 0 of 20 sites serve identical volume.** Location is not a
lever at this scale.

## Where location starts to matter

| stores | demand served | binding constraint |
|---:|---:|---|
| 20 | 14.67% | capacity |
| 60 | 44.02% | capacity |
| 100 | 73.37% | capacity |
| 120 | 88.04% | capacity |
| **140** | 98.13% | **reach** |

Reach begins to bind between **120 and 140 stores**. Below that, adding a store
adds throughput and the answer is division. Above it, stores start competing for
the same demand and where they sit decides the outcome.

## What to do

1. **Decide the store count first.** On these figures: 35 stores reach 25% of the
   market, 69 reach 50%, 123 reach 90%. Twenty stores is a 15% play whether it is
   sited well or badly.
2. **Do not fund a siting exercise below about 120 stores.** It will produce
   confident maps that do not change served volume. Fund throughput, supply and
   store count instead.
3. **When the count approaches 120, measure the effective delivery radius before
   siting.** It is the only spatial input that materially moves the answer, and
   sensitivity analysis shows rider speed and the time promise are not two
   assumptions but one: they enter only through their product. Ten minutes at
   26 km/h and fifteen minutes at 18 km/h select identical sites. That number is
   measurable from rider GPS traces rather than arguable in a workshop.
4. **Do not argue about the demand model.** Reshaping the adoption curve from
   flat to steep moves the selected sites by zero metres. It changes the business
   case for how many stores to open. It does not change where they go.
5. **If you do site, route on the network.** It is worth 3 to 8 points of
   coverage over a properly calibrated straight line method, not the 35 points a
   naive comparison suggests. Modest, real, and worth it only once you are in the
   regime where siting matters at all.

## What would change this recommendation

- **A materially higher throughput figure.** The crossover scales inversely with
  it. The anchor here is observed average throughput, not a physical ceiling, so
  the true ceiling is higher and the crossover is at fewer stores than 120.
- **A capacity constrained market.** This assumes demand exists to be served. If
  actual demand is well below the 5.5 million orders per month modelled here,
  every store count above scales down with it.
- **Objectives other than coverage.** Rent, cannibalisation, labour and
  inventory economics are not modelled. A store network optimal for coverage may
  be poor on all four.

## What this analysis cannot tell you

- **Which specific parcels to lease.** The recommended sites are not stable. They
  move by up to 2.3 km under scenario changes, and they do not settle as the
  analysis grid is refined, so the optimum value is well determined while the
  optimum argument is not.
- **Whether a site is actually available.** Candidates are filtered for physical
  plausibility from OSM land use only. Rent, lease availability, power, loading
  access and zoning decide real sites and none of them are in the data.
- **Whether the promise is deliverable.** All travel times here are rider travel
  time. Picking, packing and handover are excluded, and they consume a large
  share of a real 10 minute promise.
