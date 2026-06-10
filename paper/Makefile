PY ?= python3
ARXIV_DIR ?= ../artifacts/arxiv
USED_FIGS := $(shell grep -o 'figures/[^}]*\.pdf' main.tex | sort -u)

.PHONY: all figs pdf clean version arxiv-bundle sync-results

all: version pdf

# Refresh committed copies of the result tables and the two pipeline-only
# figures from the top-level `make results` artifacts, when present. Best-effort
# (the leading '-' ignores missing artifacts), so the paper still builds from
# its committed copies on a fresh checkout.
sync-results:
	@mkdir -p tables figures
	@[ -f ../artifacts/study/study_results.tex ] && cp -p ../artifacts/study/study_results.tex tables/study_results.tex || true
	@[ -f ../artifacts/sensitivity/sensitivity_results.tex ] && cp -p ../artifacts/sensitivity/sensitivity_results.tex tables/sensitivity_results.tex || true
	@[ -f ../artifacts/sensitivity/fig_sensitivity.pdf ] && cp -p ../artifacts/sensitivity/fig_sensitivity.pdf figures/fig_sensitivity.pdf || true
	@[ -f ../artifacts/calibration/r0_vs_rstar.pdf ] && cp -p ../artifacts/calibration/r0_vs_rstar.pdf figures/fig_calibration.pdf || true
	@[ -f ../artifacts/emergence/figures/fig_emergence.pdf ] && cp -p ../artifacts/emergence/figures/fig_emergence.pdf figures/fig_emergence.pdf || true

figs: sync-results
	MPLBACKEND=Agg $(PY) scripts/make_fig_hello.py
	MPLBACKEND=Agg $(PY) scripts/make_fig_perturbation_recovery.py
	MPLBACKEND=Agg $(PY) scripts/make_fig_nc1_contrast.py
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
	cp -p main.bbl $(ARXIV_DIR)/
	-@[ -f version.tex ] && cp -p version.tex $(ARXIV_DIR)/ || true
	@for f in $(USED_FIGS); do \
		cp -p "$$f" "$(ARXIV_DIR)/figures/"; \
	done
	@cd $(ARXIV_DIR) && zip -r ../arxiv_upload.zip main.tex macros.tex refs.bib main.bbl version.tex figures >/dev/null
	@echo "Created arXiv bundle at artifacts/arxiv_upload.zip including main.bbl and used figures: $(USED_FIGS)"
