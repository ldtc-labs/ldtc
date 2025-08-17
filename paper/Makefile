PY ?= python3

.PHONY: all figs pdf clean version

all: version pdf

figs:
	MPLBACKEND=Agg $(PY) scripts/make_fig_hello.py
	MPLBACKEND=Agg $(PY) scripts/make_fig_perturbation_recovery.py
	$(PY) scripts/make_fig_system.py
	$(PY) scripts/make_fig_loop_exchange.py
	$(PY) scripts/make_fig_dev_bootstrap.py
	$(PY) scripts/make_fig_adaptive_boundary.py
	$(PY) scripts/make_fig_meta_policy.py

pdf: figs *.tex refs.bib
	latexmk -pdf -halt-on-error main.tex

version:
	@printf '\\newcommand{\\gitversion}{%s}\n' '$(shell git describe --tags --always --dirty --broken 2>/dev/null || echo dev)' > version.tex
	@echo "Wrote version.tex"

clean:
	latexmk -C
