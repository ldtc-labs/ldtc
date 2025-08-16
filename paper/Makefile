PY ?= python3

.PHONY: all figs pdf clean version

all: version pdf

figs:
	$(PY) scripts/make_fig_hello.py

pdf: figs *.tex refs.bib
	latexmk -pdf -halt-on-error main.tex

version:
	@printf '\\newcommand{\\gitversion}{%s}\n' '$(shell git describe --tags --always --dirty --broken 2>/dev/null || echo dev)' > version.tex
	@echo "Wrote version.tex"

clean:
	latexmk -C
