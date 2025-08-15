PY := python
PIP := python -m pip

.PHONY: help install dev lock lock-dev test lint typecheck fmt run omega omega-ingress omega-cc omega-subsidy calibrate run-rstar omega-rstar keys verify-indicators clean clean-artifacts neg-controller neg-ingress neg-subsidy neg-cc docker-build docker-run figures

help:
	@echo "Targets:"
	@echo "  install        - install package (editable) with runtime deps"
	@echo "  dev            - install dev deps (pytest, black, ruff)"
	@echo "  lock           - regenerate pinned runtime requirements.txt in a temp venv"
	@echo "  lock-dev       - regenerate pinned requirements-dev.txt (dev tools) in a temp venv"
	@echo "  test           - run unit tests"
	@echo "  lint           - run ruff (if installed)"
	@echo "  typecheck      - run mypy type checks (if installed)"
	@echo "  fmt            - run black (if installed)"
	@echo "  run            - run baseline loop with R0 profile"
	@echo "  omega          - run Ω power-sag demo"
	@echo "  omega-ingress  - run Ω ingress-flood demo"
	@echo "  omega-cc       - run Ω command-conflict demo (prints Trefuse + reason)"
	@echo "  omega-subsidy  - run Ω exogenous-SoC (subsidy) demo (negative-control heuristic)"
	@echo "  calibrate      - calibrate R* thresholds and write configs/profile_rstar.yml"
	@echo "  run-rstar      - run baseline loop with R* profile"
	@echo "  omega-rstar    - run Ω power-sag with R* profile"
	@echo "  keys           - generate attestation keys"
	@echo "  verify-indicators - verify signed indicators against audit & pubkey"
	@echo "  neg-controller - negative control: controller disabled"
	@echo "  neg-ingress    - negative control: permanent exchange flood"
	@echo "  neg-subsidy    - negative control: exogenous SoC without harvest"
	@echo "  neg-cc         - negative control: command conflict/refusal demo"
	@echo "  clean          - remove build artifacts"
	@echo "  clean-artifacts- remove runtime artifacts (audits/indicators/figures)"
	@echo "  docker-build   - build Docker image"
	@echo "  docker-run     - run baseline in Docker with artifacts volume"
	@echo "  figures        - run baseline + Ω battery and emit timeline PNG/SVG, SC1 CSV, and manifest into artifacts/figures"

install:
	$(PIP) install -U pip
	$(PIP) install -e .

lock:
	@echo "Generating pinned requirements (runtime)"
	$(PY) -c 'import sys,subprocess,tempfile,shutil,os; td=tempfile.mkdtemp(); v=os.path.join(td,"v"); subprocess.check_call([sys.executable,"-m","venv",v]); ac=os.path.join(v,"bin","activate"); cmd=f". {ac} && python -m pip install -U pip setuptools wheel && pip install . && pip freeze | grep -v '^ldtc-hello-world' > requirements.txt"; subprocess.check_call(["bash","-lc",cmd]); shutil.rmtree(td)'
	@echo "Wrote requirements.txt"

lock-dev:
	@echo "Generating pinned requirements (dev)"
	$(PY) -c 'import sys,subprocess,tempfile,shutil,os; td=tempfile.mkdtemp(); v=os.path.join(td,"v"); subprocess.check_call([sys.executable,"-m","venv",v]); ac=os.path.join(v,"bin","activate"); cmd=f". {ac} && python -m pip install -U pip setuptools wheel && pip install .[dev] && pip freeze | grep -v '^ldtc-hello-world' > requirements-dev.txt"; subprocess.check_call(["bash","-lc",cmd]); shutil.rmtree(td)'
	@echo "Wrote requirements-dev.txt"

dev:
	$(PIP) install -e .[dev]

test:
	$(PY) -m pytest -q

lint:
	-ruff check .

typecheck:
	-mypy src tests scripts

fmt:
	-black src tests examples scripts

run:
	$(PY) -m ldtc.cli.main run --config configs/profile_r0.yml

omega:
	$(PY) -m ldtc.cli.main omega-power-sag --config configs/profile_r0.yml --drop 0.35 --duration 8

omega-ingress:
	$(PY) -m ldtc.cli.main omega-ingress-flood --config configs/profile_r0.yml --mult 3.0 --duration 5

omega-cc:
	$(PY) -m ldtc.cli.main omega-command-conflict --config configs/profile_r0.yml --observe 2

omega-subsidy:
	$(PY) -m ldtc.cli.main omega-exogenous-subsidy --config configs/profile_r0.yml --delta 0.2 --zero-harvest --duration 3

calibrate:
	$(PY) scripts/calibrate_rstar.py --dt 0.01 --window-sec 0.25 --method linear \
	  --baseline-sec 15 --omega-trials 6 --sag-drop 0.3 --sag-duration 8 \
	  --out configs/profile_rstar.yml \
	  --summary artifacts/calibration/rstar_summary.json

run-rstar:
	$(PY) -m ldtc.cli.main run --config configs/profile_rstar.yml

omega-rstar:
	$(PY) -m ldtc.cli.main omega-power-sag --config configs/profile_rstar.yml --drop 0.35 --duration 8

keys:
	$(PY) scripts/keygen.py

verify-indicators:
	$(PY) scripts/verify_indicators.py \
	  --ind-dir artifacts/indicators \
	  --audit artifacts/audits/audit.jsonl \
	  --pub artifacts/keys/ed25519_pub.pem

# Negative controls (configs/negative_*.yml)
neg-controller:
	$(PY) -m ldtc.cli.main run --config configs/negative_controller_disabled.yml

neg-ingress:
	$(PY) -m ldtc.cli.main omega-ingress-flood --config configs/negative_permanent_ex_flood.yml --mult 5 --duration 6

neg-subsidy:
	$(PY) -m ldtc.cli.main omega-exogenous-subsidy --config configs/negative_exogenous_soc.yml --delta 0.2 --zero-harvest --duration 3

neg-cc:
	$(PY) -m ldtc.cli.main omega-command-conflict --config configs/negative_command_conflict.yml --observe 2

clean:
	rm -rf dist build *.egg-info .pytest_cache .ruff_cache

clean-artifacts:
	rm -rf artifacts

docker-build:
	docker build -t ldtc-hello-world:latest .

docker-run:
	docker run --rm \
	  -v $(PWD)/artifacts:/app/artifacts \
	  ldtc-hello-world:latest run --config configs/profile_r0.yml

figures:
	# Run baseline, power sag (Ω), ingress flood (Ω), and command conflict (Ω)
	$(PY) -m ldtc.cli.main run --config configs/profile_r0.yml
	$(PY) -m ldtc.cli.main omega-power-sag --config configs/profile_r0.yml --drop 0.35 --duration 8
	$(PY) -m ldtc.cli.main omega-ingress-flood --config configs/profile_r0.yml --mult 3.0 --duration 5
	$(PY) -m ldtc.cli.main omega-command-conflict --config configs/profile_r0.yml --observe 2
	@echo "Figures and tables (if any) are in artifacts/figures; provenance manifest includes profile badge and audit head."
