# Progress

Running status for this project. Updated as phases complete.

## Status: phases 1 to 3 and two robustness checks complete. Phase 4 outstanding.

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

### Phase 4, sensitivity, maps and the memo: not started

Still to do:

1. The full sensitivity sweep. `config/config.yaml` already defines the grid:
   rider speed 12 to 26 km/h, threshold 8 to 15 minutes, store counts 5 to 40,
   grid resolutions 250m/500m/1000m, and the three adoption variants. The code
   paths take all of these as arguments already, so this is a runner plus a
   results table, not new modelling.
2. **Site stability across those scenarios.** `src/optimise.py::site_stability`
   is written and unit tested but has not been run on real scenario output. This
   is the output that matters most for the memo: a site chosen under every
   assumption is a different recommendation from one that appears only in the
   base case.
3. The decision memo.
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
