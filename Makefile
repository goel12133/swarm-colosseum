PYTHON ?= python3

.PHONY: workshop reproduce
# Every workshop exercise is solvable with its bundled solution (and not before).
workshop:
	$(PYTHON) workshop/check.py

# Rebuild results/ from bots/ and the seed list in the sandbox, from scratch, and diff it
# byte for byte against the committed copy. Needs Docker; ~6-8 min on 4 cores.
reproduce:
	$(PYTHON) -m colosseum.reproduce
