PYTHON ?= python3

.PHONY: workshop
# Every workshop exercise is solvable with its bundled solution (and not before).
workshop:
	$(PYTHON) workshop/check.py
