# Progress

Running status for this project. Updated as phases complete.

## Status: phases 1 to 4 and four robustness checks complete.

`make demo` runs fetch through figures. Every number in the README comes from
that run and is written to `reports/` as JSON alongside it.

## Phase by phase

### Phase 1, boundary, grid, population and demand surface: done

- 717.2 sq km boundary, 2,867 cells at 500m, 11,874,821 people, 5,547,356
  modelled orders per month. Runs in 4.9s.
- Population source resolved by testing rather than assumption. Started on
  WorldPop India (466 MB national raster) and moved to the JRC Global Human
  Settlement Layer: the WorldPop host advertises `Accept-Ranges: bytes` but
  ignores a `Range` header and returns the whole file, so a windowed remote read
  is impossible, and it served at roughly 85 KB/s against the JRC host's
  550 KB/s. GHS-POP is tiled at 1000km, so one 47 MB tile covers the city. The
  tile index is computed in `src/tiles.py`, not hardcoded.
- Population aggregation transforms pixel centres into the working CRS rather
  than reprojecting the raster, because reprojecting a count raster resamples it
  and stops the total being conserved.

### Phase 2, candidate sites and the travel time matrix: done

- 3,491 OSM land use parcels, thinned to 888 at 400m separation, capped at 400.
- 155,545 node network, 13,003.6 km of centreline. Matrix of 400 x 2,597 built
  in 5.2s with a cutoff bounded Dijkstra per candidate, avoiding 93.5% of the
  work an uncapped all pairs run would do.
- Straight line comparison built on the same candidates and cells. Straight line
  reports 2.03x the reachable pairs, and all 22,180 disagreements run in the
  same direction, which is what theory requires.

### Phase 3, the optimisation: done

- Exact MCLP via CBC covers 93.69% of demand with 20 stores and proves
  optimality in 1.1s. Greedy reaches 88.98%, leaving 5.03% on the table.
- Sites chosen on **uncalibrated** straight line distance share 0 of 20 with the
  network solution and deliver 58.65% to 63.18% against a claimed 98.81%. See the
  circuity check below: that comparison is unfair and the honest number is much
  smaller.

### Circuity calibration check: done, and it corrected the phase 3 headline

- Phase 3 compared a network matrix at 18 km/h against a straight line matrix at
  the same 18 km/h. That is a straw man: a straight line path is shorter by a
  median factor of 1.32, so at equal speed it mechanically reaches further.
  1.32 squared is about 1.74, which already accounts for most of the 2.03x reach
  inflation phase 3 reported.
- `scripts/check_circuity_calibration.py` gives the straight line method its fair
  speed and reruns the selection. **The 35 point penalty collapses to between 2.8
  and 7.9 points.**
- What survives: a real residual gap of 2.8 points at best calibration, site
  overlap of only 4 or 5 of 20, and the reason for both, which is that the detour
  factor spans p10 1.15 to p90 1.74 to p99 3.19 and no single scalar absorbs
  that.
- The README now leads with the calibrated numbers. The uncalibrated result is
  kept and shown, framed as the thing that turned out to be mostly arithmetic.

### Alternate optima robustness check: done

- `scripts/check_alternate_optima.py` resamples the straight line optimum 20
  times through weight perturbation, because MCLP alternate optima could have
  made the 0 of 20 overlap an artefact of an arbitrary tie break.
- It is not an artefact. 19 of the 20 straight line sites are identical across
  every trial, and no trial reaches the network optimum. Worst case penalty
  35.0 points, best case 30.5.

### Phase 4, sensitivity and site stability: done, and it reframed the project

- Swept speed, threshold, store count and adoption variant one parameter at a
  time. **No base case site survives every scenario**: 88 distinct sites get
  chosen across 10 comparable scenarios.
- Checked whether that was an artefact of comparing parcel identifiers rather
  than locations, since candidates sit only 400m apart. It is not:
  `check_spatial_stability.py` finds a typical shift of 662m but a worst case
  median of 2,348m, and only 7 of 20 sites stay within 2 km across all
  scenarios.
- **The adoption curve moves the sites by zero metres.** The input I had flagged
  as the weakest thing in the project turns out not to affect site selection at
  all. It rescales demand roughly monotonically with density, and a covering
  problem only cares about ordering.
- **Speed and threshold are the same parameter.** `check_effective_radius.py`
  confirms exactly: three combinations at a 3,000m effective radius give
  identical coverage, identical reachable pair counts and identical site
  selection, and likewise at 4,500m. The sensitivity has one degree of freedom
  where it looked like four.
- Conclusion the repository now leads with: do not take the 20 sites, they are
  not stable enough. Pin down the effective delivery radius first, because it is
  the only input that decides the answer and it is measurable from rider GPS
  traces rather than arguable in a workshop.

### Still outstanding

1. **Grid resolution reruns at 250m and 1000m.** The config defines them and the
   code paths take cell size as an argument, but they need a full phase 1 and
   phase 2 rebuild each, which has not been run. Until it is, I cannot say the
   conclusion is not an artefact of the 500m grid.
2. **A capacitated formulation.** See weakness 1 below. This is the largest
   remaining modelling gap.
3. The written decision memo.
4. An interactive Folium map for exploration, alongside the static figures.

## Open questions and known weaknesses

1. **The optimisation is uncapacitated.** Every store is assumed able to serve
   all the demand it covers, and the busiest cell alone carries 18,184 modelled
   orders per month. A capacitated covering formulation is the right model and
   this is not it. This is the largest remaining modelling gap.
2. **The 2020 raster biases direction, not just level.** Bengaluru's periphery
   grew faster than its core after 2020, so the surface understates the periphery
   specifically and tilts selection toward the centre.
3. **The adoption curve is the weakest input.** Four judgemental rate bands with
   no public source. The variants hold the population weighted mean fixed while
   changing curve shape, so shape and level can be told apart, but the base
   level itself is still an assumption.
4. **Population raster vintage.** Absolute figures understated by an
   unknown margin. Not corrected with an invented growth factor.
5. **One demand cell snaps 1,643m to the network.** One cell of 2,597 and it
   does not move the result, but the tail is reported rather than hidden behind
   the 40m median.
6. **Travel time excludes picking, packing and handover**, which consume a large
   share of a real 10 minute promise.
7. **The candidate filter is physical plausibility only.** Rent, lease
   availability, power, loading access and zoning decide real sites and none of
   them are in OSM.
8. **No congestion profile.** One speed, whole city, all day.
