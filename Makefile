VENV := .venv
PY := $(VENV)/bin/python

.PHONY: help setup fetch phase1 phase2 phase3 phase4 phase5 robustness grid figures map demo test lint clean

help:
	@echo "setup   create the virtualenv and install dependencies"
	@echo "fetch   download the population raster tile into data/raw/"
	@echo "phase1  boundary, grid, population, demand surface"
	@echo "phase2  candidates, travel time matrices, straight line comparison"
	@echo "phase3  the optimisation and the straight line penalty"
	@echo "phase4  sensitivity sweep and site stability"
	@echo "phase5  capacitated formulation and the binding constraint"
	@echo "grid    rerun at 125m, 250m, 500m and 1000m"
	@echo "figures every figure in the README"
	@echo "map     interactive map, written to reports/ and not committed"
	@echo "demo    fetch and every phase, end to end"
	@echo "test    run the test suite"
	@echo "lint    pyflakes and black --check"

setup:
	python3 -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt -r requirements-dev.txt

fetch:
	$(PY) scripts/fetch_data.py

phase1:
	$(PY) scripts/run_phase1.py

phase2:
	$(PY) scripts/run_phase2.py

phase3:
	$(PY) scripts/run_phase3.py

phase4:
	$(PY) scripts/run_phase4.py

phase5:
	$(PY) scripts/run_phase5_capacity.py
	$(PY) scripts/check_binding_constraint.py

grid:
	$(PY) scripts/run_grid_sensitivity.py

robustness:
	$(PY) scripts/check_alternate_optima.py --trials 20
	$(PY) scripts/check_circuity_calibration.py
	$(PY) scripts/check_spatial_stability.py
	$(PY) scripts/check_effective_radius.py

map:
	$(PY) scripts/make_interactive_map.py

figures:
	$(PY) scripts/make_figures.py

demo: fetch phase1 phase2 phase3 phase4 phase5 figures
	@echo ""
	@echo "Done. Summaries in reports/, figures in reports/figures/."

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m pyflakes src scripts tests
	$(PY) -m black --check src scripts tests

clean:
	rm -rf data/interim/* data/processed/* reports/*.json
	find . -name __pycache__ -type d -exec rm -rf {} +
