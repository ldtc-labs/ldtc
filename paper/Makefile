PY ?= python3
ARXIV_DIR ?= ../artifacts/arxiv
USED_FIGS := $(shell grep -o 'figures/[^}]*\.pdf' main.tex | sort -u)

.PHONY: all figs pdf clean version arxiv-bundle

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

arxiv-bundle: pdf
	rm -rf $(ARXIV_DIR)
	mkdir -p $(ARXIV_DIR)/figures
	cp -p main.tex $(ARXIV_DIR)/
	cp -p macros.tex $(ARXIV_DIR)/
	cp -p refs.bib $(ARXIV_DIR)/
	@for f in $(USED_FIGS); do \
		cp -p "$$f" "$(ARXIV_DIR)/figures/"; \
	done
	@cd $(ARXIV_DIR) && zip -r ../arxiv_upload.zip main.tex macros.tex refs.bib figures >/dev/null
	@echo "Created arXiv bundle at artifacts/arxiv_upload.zip with used figures: $(USED_FIGS)"
