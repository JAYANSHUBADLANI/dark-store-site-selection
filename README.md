# Dark Store Site Selection, Bengaluru

[![tests](https://github.com/JAYANSHUBADLANI/dark-store-site-selection/actions/workflows/pytest.yml/badge.svg)](https://github.com/JAYANSHUBADLANI/dark-store-site-selection/actions/workflows/pytest.yml)

Where should a quick commerce operator put its next 20 dark stores so that the
most demand sits inside a 10 minute delivery promise.

I built this to do one thing properly that most "where should we put our stores"
analyses do badly: **measure travel time along the actual road network rather
than in a straight line.**

I got a striking answer, then spent longer attacking it than building it. Two
of those attacks landed, and they matter more than the original result:

> **1. The question was malformed.** Asking where 20 dark stores go assumes reach
> is the binding constraint. It is not. At 20 stores, throughput binds
> completely: every store runs at exactly its capacity, so any 20 reachable
> sites serve identical demand and **location does not affect the answer at
> all**. The covering model reports 93.69% coverage while those stores can
> physically serve **14.7%** of demand. Location only starts to decide anything
> at around **120 to 140 stores**.
>
> **2. The headline comparison was a straw man.** Routing on the real network
> beats a **properly calibrated** straight line approximation by 2.8 to 7.9
> points, not the 35 points I first reported, because my first comparison gave
> both methods the same speed when practice calibrates the straight line one
> down.

Both are the kind of thing a reader finds for themselves if the author does not,
so they go first rather than in a limitations section at the bottom.

Everything below comes from running the pipeline. No figure in this README was
typed in by hand.

![Selected sites](reports/figures/selected_sites.png)

## Capacity, and why the siting question was the wrong one

The covering model asks whether a store can **reach** a cell. It never asks
whether it can **fulfil** it. Those come apart badly here.

A dark store's throughput is a real limit and I do not have a sourced figure for
it, so I swept it rather than inventing one. Placing 20 stores:

| capacity per store per month | demand served | capacity ceiling | utilisation | sites shared with the covering solution |
|---:|---:|---:|---:|---:|
| 20,000 | 7.21% | 7.21% | 1.000 | 1 of 20 |
| 30,000 | 10.82% | 10.82% | 1.000 | 1 of 20 |
| **40,700** | **14.67%** | 14.67% | 1.000 | 0 of 20 |
| 60,000 | 21.63% | 21.63% | 1.000 | 0 of 20 |
| 80,000 | 28.84% | 28.84% | 1.000 | 0 of 20 |

The 40,700 row is the anchor, and unlike most numbers in this section it is
derived rather than assumed: Blinkit reported 273.9 million orders in Q4 FY26
across 2,243 dark stores, which is roughly 40,700 orders per store per month.
Four caveats travel with it and they are in `config/config.yaml` in full: it is
**observed average throughput, not a capacity ceiling**, so using it as a hard
cap is conservative; it is a national average, not Bengaluru; it is the market
leader, so smaller operators run lower; and I could not open the primary filing,
only several independent outlets reporting the same shareholders letter and
agreeing. The sweep stays for that reason.

**Served demand equals the capacity ceiling exactly, at every level, with
utilisation of 1.000.** Every store fills up. That has a blunt consequence: at
this store count the optimiser's location choice **changes nothing**. Any 20
sites with enough demand within reach produce the same served demand, which in a
city this dense is nearly all of them. The covering solution and the capacitated
solution share 0 or 1 sites out of 20 and it does not matter, because they serve
identical volume.

So the model that reports 93.69% coverage describes 20 stores that can serve
**14.7%** of demand.

### Where the constraint actually flips

Capacity cannot bind forever. Add enough stores and there stops being enough
reachable demand to fill them all.

| stores | served | ceiling | utilisation | binding constraint |
|---:|---:|---:|---:|---|
| 20 | 14.67% | 14.67% | 1.000 | capacity |
| 60 | 44.02% | 44.02% | 1.000 | capacity |
| 100 | 73.37% | 73.37% | 1.000 | capacity |
| 120 | 88.04% | 88.04% | 1.000 | capacity |
| 140 | 98.13% | 100% | 0.955 | **reach** |
| 200 | 98.24% | 100% | 0.670 | reach |

**Reach begins to bind between 120 and 140 stores**, at 40,700 orders per store
per month. That single number reconciles the whole repository:

- **Below roughly 120 stores, this is not a siting problem.** It is a store count
  problem, and the answer is arithmetic: demand divided by throughput. 25% of the
  market needs 35 stores, 50% needs 69, 90% needs 123. All the covering
  machinery, the road network, the Dijkstra pruning, the circuity analysis, is
  answering a question that is not binding.
- **Above it, the covering model is the right tool**, and everything else in this
  repository applies.

The store count where this flips is close to the scale the real Bengaluru market
operates at across all players, which is a reassuring sanity check on the order
of magnitude, though not a validation of any specific number.

**Caveat that limits all of this:** the crossover scales inversely with the
throughput figure. At 30,000 orders per store it sits near 180 stores; at 40,700
it sits near 130. What does not depend on that number is the structural finding:
there is a store count below which location is irrelevant, and a covering model
cannot tell you whether you are below it.

## The result I first got, and why I did not keep it

Solving the same problem twice, changing only how travel time is measured:

| | chosen on road network | chosen on straight line |
|---|---:|---:|
| Coverage it claims | 93.69% | 98.81% |
| Coverage it actually delivers | 93.69% | 58.65% |
| Sites in common | | **0 of 20** |

A 35 point gap, and two completely disjoint site sets. It is a striking result
and it is close to meaningless, because **both matrices used the same speed of
18 km/h.**

A straight line path is shorter than the road path between the same two points,
here by a median factor of 1.32. Applying the same speed to a shorter distance
mechanically produces a shorter time and therefore more reach. Reach scales
roughly with the square of the radius, so 1.32 squared, about 1.74, already
predicts most of the 2.03x reach inflation I measured. **The result was largely
arithmetic, not discovery.**

And no practitioner works that way. Straight line distance is used in real
logistics with a **circuity factor**: the speed is calibrated downward so
straight line time approximates road time on average. The fair comparison
calibrates the straight line method before beating it.

## The calibrated comparison

`scripts/check_circuity_calibration.py` gives the straight line method its fair
speed and reruns the whole selection.

| straight line variant | implied speed | claims | actually delivers | shortfall vs network | shared sites |
|---|---:|---:|---:|---:|---:|
| Uncalibrated | 18.0 km/h | 98.81% | 58.65% | 35.0 pts | 0 of 20 |
| Calibrated to median detour | 13.7 km/h | 95.58% | 85.80% | 7.9 pts | 4 of 20 |
| Calibrated to mean detour | 12.6 km/h | 91.80% | 90.29% | 3.4 pts | 5 of 20 |
| Over-calibrated, 1.5x | 12.0 km/h | 88.65% | 90.90% | **2.8 pts** | 5 of 20 |

**The headline collapses from 35 points to between 3 and 8.** A calibrated
straight line approximation is, on this city, a reasonable tool. If someone tells
me they sited stores with haversine distance and a circuity factor, I no longer
have grounds to tell them they are badly wrong.

What survives is smaller and better supported:

- **A real residual gap.** Even the best calibrated variant gives up 2.8 points
  of coverage. On 5.5 million modelled orders per month that is about 155,000
  orders sitting outside the promise that need not be.
- **Different sites, still.** The calibrated methods share only 4 or 5 of 20
  sites with the network solution. The coverage numbers converge; the actual
  recommendation does not.
- **The reason it cannot be fully calibrated away.** The detour factor is not a
  constant. Its spread across candidate to cell pairs is p10 1.15, p50 1.32,
  p90 1.74, p99 3.19. A single scalar cannot absorb that, because the high
  circuity pairs are exactly the ones that sit across the lakes, railway lines
  and limited access corridors that decide where a 10 minute boundary really
  falls. **Network routing earns its place on the variance of circuity, not on
  its average.**
- **Over-calibration flips the error.** At 1.5x the straight line method claims
  88.65% and delivers 90.90%, so it becomes conservative rather than optimistic.
  Useful to know if the intended failure direction matters.

## The uncalibrated result is at least not a solver artefact

Before the circuity test above, I checked a different way the uncalibrated
result could have been spurious. The maximal covering problem has many alternate
optima: when 400 candidates can between them reach 98% of a city, a great many
different sets of 20 hit the same objective value, and the solver returns
whichever it reaches first. So "0 of 20 sites in common" could have been an
artefact of an arbitrary tie break.

`scripts/check_alternate_optima.py` resamples the straight line optimum 20 times
by perturbing the demand weights by up to 0.1%, which breaks ties differently
without meaningfully changing the problem, and scores every resulting site set
against network truth.

| | |
|---|---:|
| Network optimum | 93.69% |
| Best uncalibrated straight line solution, scored on the network | 63.18% |
| Worst straight line solution | 58.65% |
| Trials reaching the network optimum | 0 of 20 |
| Distinct sites used across all 20 trials | 21 |
| Sites common to every trial | 19 |

The straight line solution is **stable**, not arbitrary: 19 of its 20 sites are
identical across every trial, and no trial reaches the network optimum. So the
uncalibrated comparison is a real property of that specification rather than a
solver coincidence. It is just a comparison against a specification nobody
should use, which is what the circuity test above established and why the
calibrated numbers are the ones I lead with.

## Why a single circuity factor cannot fix it

![Reach comparison](reports/figures/reach_comparison.png)

The left panel shows a property, not a discovery: every candidate sits below the
equal reach line because a road path can never be shorter than the straight line
between the same two points, so at equal speed straight line distance **can only
overstate reach, never understate it**. The pipeline confirms it holds with no
exceptions: of 1,038,800 candidate to cell pairs, 22,180 disagree, and **all
22,180** run in the same direction. Zero go the other way. That is a useful
correctness check on the matrices and nothing more, since a calibrated speed
removes most of this bias by construction.

The right panel is the part that matters. The median detour factor is **1.32x**,
which is exactly what a circuity factor calibrates away. But the factor is not a
constant:

| percentile | detour factor |
|---|---:|
| p10 | 1.15 |
| p50 | 1.32 |
| p90 | 1.74 |
| p99 | 3.19 |
| max | 33 |

Calibration sets one number against a distribution that spans nearly threefold
between its 10th and 90th percentile. The high circuity pairs are not scattered
at random either: they are cells sitting across the lakes, railway lines and
limited access corridors that Bengaluru has plenty of, which is precisely where a
10 minute boundary is decided. **That variance, not the average, is what network
routing buys.**

## The demand surface

![Demand surface](reports/figures/demand_surface.png)

| | |
|---|---:|
| City boundary (BBMP, from OSM) | 717.2 sq km |
| Analysis grid | 2,867 cells at 500m |
| Population, GHS-POP 2020 | 11,874,821 |
| Households at 4.3 per household | 2,761,018 |
| Population weighted adoption rate | 0.251 |
| Modelled orders per month | 5,547,356 |

The chain is short and every link is a proxy:

    population -> households -> adopting households -> orders per month

**The adoption rate is the weakest input in this project and I want to be
explicit about it.** Quick commerce adoption concentrates in dense, younger,
higher income neighbourhoods, and there is no public dataset of it at grid
level. I use population density as the only available proxy, with four
judgemental rate bands in `config/config.yaml`. They are not sourced. They are
the reason the sensitivity analysis exists.

As an outside check, 5.5 million orders per month for Bengaluru is the right
order of magnitude against the disclosed national order volumes of the listed
players, which is reassuring about the level but says nothing about whether the
rate is distributed correctly across the city. Distribution is what site
selection actually depends on.

![Population distribution](reports/figures/population_distribution.png)

Population across cells is heavily skewed: the median populated cell holds 450
people and the mean holds 4,173. I plotted this rather than quoting a single
number because the skew is the thing that makes a covering problem interesting.
If demand were uniform, site selection would be a packing exercise.

## Method

### Population, without resampling it

GHS-POP values are residential population **counts** per 100m cell, not a
density. Two consequences drive the implementation:

- Aggregating to the analysis grid means **summing** the pixels inside each
  cell. Averaging or bilinear sampling would be wrong.
- The raster is in Mollweide and the analysis is in UTM 43N, but I **never
  reproject the raster**. Reprojecting a count raster resamples it, resampling
  redistributes counts between cells, and the total stops being conserved.
  Instead I transform the pixel **centres** as points and join them to the grid.
  Every pixel lands in exactly one cell, and nothing is invented or lost.

I also switched population source mid build, for reasons I tested rather than
assumed. I started on WorldPop, whose India raster is 466 MB. Its host advertises
`Accept-Ranges: bytes` but ignores a `Range` header and returns the whole file,
so a windowed remote read is impossible, and it served at roughly 85 KB/s against
the JRC host's 550 KB/s. GHS-POP is distributed as 1000km tiles, so one 47 MB
tile covers the city. The tile index is computed from a coordinate in
`src/tiles.py`, so pointing this at another city is a config change.

### The road network

| | |
|---|---:|
| Nodes | 155,545 |
| Edges (directed) | 393,912 |
| Centreline length | 13,003.6 km |
| Effective rider speed | 18 km/h |

OSMnx returns a MultiDiGraph, so a two way street contributes two edges. Summing
edge lengths gives 24,251.1 km, which is roughly double the real centreline
length. Reporting that as "road length" would overstate the network by a factor
of two, so both numbers are computed and the undirected one is the one quoted.
I have not cross checked 13,004 km against BBMP's own published road length, so
treat it as what OSM contains for this boundary rather than as a verified
municipal figure.

I use a single effective speed rather than OSM `maxspeed` tags. Those tags are
free flow legal limits, most Bengaluru links do not carry one, and a two wheeler
in city traffic travels at neither. One stated, sensitivity tested number is more
honest than a per link value that looks precise and is not.

### The travel time matrix, and why it is cheap

The naive formulation is all pairs shortest path between 400 candidates and
2,597 cells over a 155,545 node network. But anything beyond the delivery promise
is irrelevant to a covering problem, so I run **one cutoff bounded Dijkstra per
candidate** instead, which never expands the far side of the city.

| | |
|---|---:|
| Matrix shape | 400 x 2,597 |
| Build time | 5.2 s |
| Node expansions | 4,060,456 |
| Expansions an uncapped run would need | 62,218,000 |
| Work avoided | **93.5%** |

Candidate centroids snap to the network at a median of 48m (p95 167m, max 472m).
Demand cells snap at a median of 40m, but p95 is 246m and the **worst is
1,643m**. That last cell is being modelled as if it sat on a road 1.6 km from
where it actually is. It is one cell out of 2,597 and it does not move the
result, but a snap distance is a modelling error and I would rather report the
tail than quote the median and move on.

### The optimisation

The Maximal Covering Location Problem, written out so it can be checked:

    sets
        I    demand cells, weight w_i
        J    candidate sites
        N_i  subset of J reaching cell i within the threshold

    variables
        x_j in {0,1}   open a store at j
        y_i in {0,1}   cell i is covered

    maximise    sum_i w_i * y_i
    subject to  y_i <= sum_{j in N_i} x_j    for all i
                sum_j x_j = p

Solved with CBC through PuLP. On this instance it **proves optimality in 1.1
seconds**, so the reported optimum is a proven one and not an incumbent that hit
a time limit. The code reports which of those two it got, because presenting an
incumbent as an optimum is exactly the kind of quiet overclaim this project is
trying to avoid.

I also implemented a greedy heuristic, not as a fallback but as a baseline:

| | coverage | time |
|---|---:|---:|
| Exact (CBC) | 93.69% | 1.1 s |
| Greedy | 88.98% | 0.02 s |

Greedy leaves **5.03%** of the achievable demand on the table. That number is why
the exact solve is worth running, and `tests/test_optimise.py` pins a constructed
instance where greedy provably reaches 9 against the optimum's 12, so the gap is
a property of the algorithm rather than an accident of this data.

### Candidate sites

Candidates come from OSM `landuse` polygons tagged retail, commercial or
industrial: 3,491 parcels, thinned to 888 by a 400m minimum separation, then
capped at the 400 with the most demand within reach. Without the separation
constraint the set piles up along a few commercial strips and the optimiser
spends its budget distinguishing between sites 30m apart.

This filters for physical plausibility only. It says nothing about whether a
lease is available, what the rent is, whether the landlord will take a warehouse
tenant, whether there is three phase power and backup, or whether loading a fleet
of two wheelers at 7am survives contact with the neighbours. **The optimiser
answers "where is best given coverage", not "where can you actually open".**

## Coverage against store count

![Coverage curve](reports/figures/coverage_curve.png)

| stores | coverage |
|---:|---:|
| 5 | 42.82% |
| 10 | 67.59% |
| 15 | 80.69% |
| 20 | 88.98% |
| 30 | 96.99% |
| 40 | 98.13% |

Diminishing returns set in hard after about 30 stores. These are greedy
solutions, so each is a lower bound on what that store count can achieve.

## Sensitivity, and the finding that reframed the project

I swept rider speed, delivery threshold, store count and the adoption curve, one
parameter at a time, then asked how many of the 20 recommended sites survive.

**None of them.** Across 10 comparable scenarios, 88 distinct sites get chosen
and not one appears in every scenario. My first thought was that the metric was
too strict, since it compares parcel identifiers and candidates are only 400m
apart, so moving a store next door scores as total disagreement.
`scripts/check_spatial_stability.py` tests that by measuring distance instead of
identity, and the instability is real: under a typical scenario change the
nearest chosen site is 662m away, but in the worst case the median base site
moves 2,348m and one moves 4,681m. Only 7 of 20 stay within 2 km of a chosen
site across every scenario.

But the breakdown of *which* scenarios move the sites is the interesting part:

| scenario | median shift of a base site | sites within 1 km |
|---|---:|---:|
| Adoption curve flat | **0 m** | 20 of 20 |
| Adoption curve steep | **0 m** | 20 of 20 |
| Threshold 12 min | 515 m | 14 of 20 |
| Speed 15 km/h | 613 m | 14 of 20 |
| Threshold 8 min | 704 m | 15 of 20 |
| Speed 22 km/h | 703 m | 12 of 20 |
| Speed 12 km/h | 1,008 m | 10 of 20 |
| Threshold 15 min | 1,823 m | 5 of 20 |
| Speed 26 km/h | 1,824 m | 4 of 20 |

**The adoption curve does not move the answer at all.** That is the assumption I
had flagged as the weakest thing in the project, the one with no public source
and four judgemental numbers in a config file. Reshaping it from flat to steep
changes the selected sites by zero metres. It changes how much demand a solution
is credited with, but not where the stores go, because it rescales demand
roughly monotonically with density and the covering problem only cares about the
ordering.

What does move the answer is travel radius. And the last two rows of that table
are suspiciously alike: 15 minutes at 18 km/h shifts sites 1,823m, 10 minutes at
26 km/h shifts them 1,824m.

### Speed and threshold are the same parameter

A covering constraint only ever asks whether a cell is within `speed x
threshold` metres of road distance. So the two should enter the model only
through their product, and `scripts/check_effective_radius.py` confirms it
exactly:

| speed | threshold | effective radius | coverage | reachable pairs | sites shared |
|---:|---:|---:|---:|---:|---:|
| 18.0 km/h | 10 min | 3,000 m | 93.69% | 21,627 | reference |
| 12.0 km/h | 15 min | 3,000 m | 93.69% | 21,627 | 20 of 20 |
| 22.5 km/h | 8 min | 3,000 m | 93.69% | 21,627 | 20 of 20 |
| 18.0 km/h | 15 min | 4,500 m | 98.84% | 52,351 | reference |
| 27.0 km/h | 10 min | 4,500 m | 98.84% | 52,351 | 20 of 20 |
| 13.5 km/h | 20 min | 4,500 m | 98.84% | 52,351 | 20 of 20 |

Identical coverage, identical reachable pair counts, identical site selection.
**The sensitivity analysis has one degree of freedom where it looked like it had
four.**

### Grid resolution: the coverage number converges, the sites do not

A 500m cell is 1.67 minutes of travel at 18 km/h, so the coverage boundary is
only resolved to within a couple of minutes. I reran the whole selection at
125m, 250m and 1000m, holding the candidate set fixed so only the demand
representation changes.

| cell size | cells | coverage | identical sites vs base | median site shift | within 1 km |
|---:|---:|---:|---:|---:|---:|
| 125 m | 37,350 | 92.22% | 8 of 20 | 766 m | 16 of 20 |
| 250 m | 9,921 | 92.73% | 10 of 20 | 355 m | 17 of 20 |
| 500 m | 2,597 | 93.69% | base | | |
| 1000 m | 675 | 95.15% | 4 of 20 | 789 m | 13 of 20 |

All four solves proved optimality, the finest in 54.9 seconds.

**The coverage estimate converges cleanly.** Successive refinements change it by
less each time, and by almost exactly half each time:

| refinement | change in coverage |
|---|---:|
| 1000 m to 500 m | -0.0146 |
| 500 m to 250 m | -0.0097 |
| 250 m to 125 m | -0.0050 |

That is what a well behaved discretisation looks like, and it extrapolates to a
converged value near 92%. It also shows the direction of the bias: coarser grids
credit more demand as covered, because a 1000m cell hands a full square
kilometre to a store that only reaches its centroid. **The 93.69% quoted
throughout this README is therefore mildly optimistic, and 92.22% at 125m is the
more honest figure.**

**The site selection does not converge.** The median site shift is 355m at 250m
but 766m at 125m, which is not a sequence settling down, and 766m is well above
the 400m separation floor between candidates, so it is not an artefact of
candidate granularity either.

I had earlier concluded from the 250m and 1000m runs alone that the sites were
converging. The 125m run falsifies that, and the way it was hidden is worth
recording: my first version of this check took the **minimum** shift across the
finer grids, which reports only the grid that happens to agree. It now takes the
worst.

So the honest statement is a split one: **the optimum value is well determined
and the optimum argument is not.** That is consistent with everything else in
this repository, since a covering problem with many near optimal solutions will
have a stable objective and an unstable argmax, and it is another reason not to
hand over the 20 pins.

### So what should someone actually do with this

Not take the 20 sites. They are not stable enough to hand over as a
recommendation, and this repository should not pretend otherwise.

What it does support is narrower and more useful:

0. **Check whether you are even in the siting regime.** Divide demand by store
   throughput. If that number is far above your planned store count, location is
   not your constraint and no amount of spatial optimisation will change your
   served volume. On these figures that threshold is around 120 to 140 stores,
   and a 20 store plan is nowhere near it.
1. **Then pin down the effective delivery radius.** It is the only spatial input
   that materially decides the answer, and it is measurable: it comes out of
   rider GPS traces, not out of a workshop. Every hour spent refining the demand
   model before that number is settled is wasted.
2. **Stop arguing about the adoption curve.** It changes the business case for
   how many stores to open. It does not change where they go.
3. **Treat network routing as worth 3 to 8 points**, not 35, and decide whether
   building that pipeline is worth it on those terms.
4. **Do not run this on a 1 km grid**, and read the coverage figure as
   converging to roughly 92% rather than the 93.69% the 500m grid reports.

That is a smaller claim than the one I set out to make, and it is the one the
evidence supports.

## What this project does not establish

- **There is no ground truth.** No held out test set says the site selection was
  correct. The deliverable is a decision framework with its sensitivities
  exposed, not a validated optimum.
- **The case for network routing here is 3 to 8 points of coverage, not 35.**
  A calibrated straight line approximation is a reasonable tool on this city.
  The residual gain is real but modest, and anyone deciding whether to build a
  routing pipeline should weigh it against that number rather than the headline
  the uncalibrated comparison produces.
- **Store throughput is an observed average, not a capacity ceiling.** The
  anchor figure comes from disclosed order volumes divided by disclosed store
  counts, so it is what stores actually do rather than what they could do. Real
  capacity is higher, which pushes the crossover to fewer stores than the 120 to
  140 reported here.
- **The 2020 population raster biases the answer directionally, not just in
  level.** Bengaluru's periphery has grown faster than its core since 2020, so an
  unadjusted 2020 surface understates the periphery specifically and tilts site
  selection toward the centre.
- **Reported coverage carries a resolution bias.** Coarser grids credit more
  demand as covered, so the headline 93.69% is optimistic and the converged
  value is near 92%. The site selection does not converge at all across
  resolutions, which is a separate and more serious problem than the bias.
- **The adoption curve is judgemental.** Its four rate bands are the least
  defensible numbers here, and site selection depends on them.
- **The population raster is the 2020 epoch.** Bengaluru has grown since, so
  absolute figures are understated by an unknown margin. I did not correct this
  with an invented growth factor.
- **Travel time is rider travel time only.** It excludes picking, packing,
  handover and waiting at the door, which in practice consume a large share of a
  10 minute promise. A 10 minute travel budget is not a 10 minute delivery.
- **One speed for the whole city, all day.** No congestion profile, no peak and
  off peak, no difference between an arterial and a lane.
- **Coverage is not the only objective.** Real siting trades coverage against
  rent, labour, cannibalisation between stores and inventory economics. None of
  those are modelled.

## Running it

```bash
make setup       # virtualenv and dependencies
make fetch       # download the 47 MB GHS-POP tile into data/raw/
make phase1      # boundary, grid, population, demand surface
make phase2      # candidates, travel time matrices, straight line comparison
make phase3      # the optimisation and the straight line penalty
make phase4      # sensitivity sweep and site stability
make phase5      # capacity, and where the binding constraint flips
make robustness  # the four checks that corrected the headline
make grid        # rerun at 125m, 250m, 500m and 1000m
make figures     # every figure in this README
make map         # interactive map for exploring, not committed
make test        # 23 tests
```

`make demo` reproduces everything this README reports, in roughly ten minutes.
`make quick` runs the phases only, in about four.

### It has actually been tested

I deleted every derived artefact, including the cached road network, and ran
`make demo` from scratch. It exited cleanly, re-pulled the 155,545 node network
from OpenStreetMap, and regenerated all ten report files **bit for bit identical**
to the versions committed here, comparing every numeric field. Nothing in this
README depends on state that only exists on the machine it was built on.

That test found one real problem, which is why it was worth running: `make demo`
did not run the robustness checks, so a reader could reproduce the phases but
not the circuity calibration that the headline result comes from. `demo` now
includes them, and `quick` is the phases-only target.

Raw rasters, the cached road network and the travel time matrices stay out of
version control. `scripts/fetch_data.py` reproduces the only external download.

## Repository layout

```
config/config.yaml     every assumption, cited. No magic numbers in code.
src/tiles.py           GHSL tile index arithmetic
src/population.py      raster to grid, without resampling counts
src/demand.py          the demand chain and its sensitivity variants
src/network.py         road network, cutoff Dijkstra matrix, haversine matrix
src/candidates.py      OSM land use parcels, thinning, capping
src/optimise.py        MCLP exact and greedy, capacitated variant, stability
src/viz.py             figures
scripts/               one runner per phase, plus six robustness checks:
                       alternate optima, circuity calibration, spatial
                       stability, effective radius, grid resolution,
                       binding constraint
docs/decision_memo.md  the memo this was built to produce
Makefile               make demo reproduces every number in this README
reports/               summary JSON per phase and per check, figures
tests/                 23 tests
```

## Status

Phases 1 to 5 and six robustness checks are complete, and every number above
comes from a run. See `PROGRESS.md` for what is left.

## The memo

`docs/decision_memo.md` is the deliverable this was built to produce. Its
recommendation is not the one the brief expected: do not spend a month choosing
20 locations, because at 20 stores the location choice does not change what they
deliver.

## Data sources

- **Population**: JRC Global Human Settlement Layer, GHS-POP R2023A, 100m,
  epoch 2020, tile R8_C26. Schiavina, Freire, Carioli, MacManus (2023),
  European Commission Joint Research Centre.
  https://ghsl.jrc.ec.europa.eu/ghs_pop2023.php
- **Road network and land use**: OpenStreetMap, via OSMnx, pulled 2026-08-28.
  Copyright OpenStreetMap contributors, ODbL.
- **City boundary**: OSM Nominatim, "Bengaluru, Karnataka, India".
- **Household size**: Census of India 2011, House Listing and Housing Census,
  Karnataka urban average.
- **Store throughput anchor**: Blinkit Q4 FY26, 273.9 million orders across
  2,243 dark stores, from Eternal Ltd's Q4 FY26 shareholders letter as reported
  in April 2026. Taken from several independent outlets reporting the same
  letter rather than read off the primary filing, which I could not open. See
  the caveats in `config/config.yaml`.

## License

MIT. See `LICENSE`.
