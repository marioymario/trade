COMPOSE     = docker compose
COMPOSE_GPU = docker compose -f docker-compose.yml -f docker-compose.gpu.yml

# Storage namespace for data/raw + data/processed.
# Priority:
#   1) environment/CLI DATA_TAG (if you pass DATA_TAG=... make ...)
#   2) environment CCXT_EXCHANGE
#   3) coinbase
#
# NOTE: `?=` already handles (1) automatically: if DATA_TAG is set in the
# environment or on the make command line, this assignment is skipped.
DATA_TAG ?= $(if $(CCXT_EXCHANGE),$(CCXT_EXCHANGE),coinbase)

# --- IMPORTANT ---
# docker compose does NOT automatically pass host env into containers.
# We must explicitly forward the vars we depend on.
RUN_ENV = \
	--env DATA_TAG \
	--env CCXT_EXCHANGE \
	--env SYMBOL \
	--env TIMEFRAME \
	--env DRY_RUN \
	--env LOOP_SLEEP_SECONDS \
	--env MIN_BARS \
	--env MAX_ORDER_SIZE \
	--env FEE_BPS \
	--env SLIPPAGE_BPS \
	--env COOLDOWN_BARS

.PHONY: services config \
        build \
        jupyter-up jupyter-down jupyter-logs \
        live-up live-down live-restart live-logs live-status \
        logs logs-all \
        shell shell-gpu \
        smoke sanity env \
        smoke-gpu sanity-gpu correctness-gpu data-quality-gpu features-check-gpu state-check-gpu \
        backtest eq report report-gpu gpu-check \
        health health_strict status tag-now

# ----------------------------
# Discover / inspect
# ----------------------------
services:
	@$(COMPOSE) config --services

config:
	@$(COMPOSE) config

live-status:
	@$(COMPOSE) ps

# ----------------------------
# Build
# ----------------------------
build:
	$(COMPOSE) build

# ----------------------------
# Jupyter/tooling
# ----------------------------
jupyter-up:
	$(COMPOSE) up -d --build trade

jupyter-down:
	$(COMPOSE) down

jupyter-logs:
	$(COMPOSE) logs -f --tail=200 trade

# ----------------------------
# LIVE paper loop controls
# NOTE: for paper, env must be wired in docker-compose.yml (see note below)
# ----------------------------
live-up:
	$(COMPOSE) up -d --build paper

live-down:
	$(COMPOSE) stop paper

live-restart:
	$(COMPOSE) restart paper

live-logs:
	$(COMPOSE) logs -f --tail=200 paper

logs: live-logs

logs-all:
	$(COMPOSE) logs -f --tail=200

# ----------------------------
# Dev shells
# ----------------------------
shell:
	$(COMPOSE) run --rm $(RUN_ENV) trade bash

shell-gpu:
	$(COMPOSE_GPU) run --rm $(RUN_ENV) trade bash

# ----------------------------
# Quick checks (CPU)
# ----------------------------
env:
	$(COMPOSE) run --rm $(RUN_ENV) trade python -c "from files.config import load_alpaca_config; load_alpaca_config(); print('Alpaca env OK')"

smoke:
	$(COMPOSE) run --rm $(RUN_ENV) trade python -m files.main_smoke

sanity:
	$(COMPOSE) run --rm $(RUN_ENV) trade python -m files.main_sanity_check

report:
	$(COMPOSE) run --rm $(RUN_ENV) --env REPORT_DAYS_TAIL --env REPORT_EXCHANGE --env REPORT_SYMBOL --env REPORT_TIMEFRAME trade \
	  python -m files.utils.trade_report

# ----------------------------
# GPU variants
# ----------------------------
smoke-gpu:
	$(COMPOSE_GPU) run --rm $(RUN_ENV) trade python -m files.main_smoke

sanity-gpu:
	$(COMPOSE_GPU) run --rm $(RUN_ENV) trade python -m files.main_sanity_check

correctness-gpu:
	$(COMPOSE_GPU) run --rm $(RUN_ENV) trade python -m files.main_correctness_check

data-quality-gpu:
	$(COMPOSE_GPU) run --rm $(RUN_ENV) trade python -m files.main_data_quality_check

features-check-gpu:
	$(COMPOSE_GPU) run --rm $(RUN_ENV) trade python -m files.main_features_check

state-check-gpu:
	$(COMPOSE_GPU) run --rm $(RUN_ENV) trade python -m files.main_state_check

report-gpu:
	$(COMPOSE_GPU) run --rm $(RUN_ENV) --env REPORT_DAYS_TAIL --env REPORT_EXCHANGE --env REPORT_SYMBOL --env REPORT_TIMEFRAME trade \
	  python -m files.utils.trade_report

gpu-check:
	$(COMPOSE_GPU) run --rm trade nvidia-smi
	$(COMPOSE_GPU) run --rm trade python -c "import tensorflow as tf; print(tf.config.list_physical_devices('GPU'))"

# ----------------------------
# Backtest + Equivalence
# ----------------------------
backtest:
	$(COMPOSE) run --rm $(RUN_ENV) trade python -m files.backtest \
	  --runid $${RUNID} \
	  $$( [ -n "$$START_TS_MS" ] && printf -- " --start-ts-ms %s" "$$START_TS_MS" ) \
	  $$( [ -n "$$END_TS_MS" ] && printf -- " --end-ts-ms %s" "$$END_TS_MS" )

eq:
	$(COMPOSE) run --rm $(RUN_ENV) trade python -m files.main_live_vs_backtest_equivalence \
	  --symbol BTC_USD \
	  --timeframe 5m \
	  --live-tag "$(DATA_TAG)" \
	  --bt-tag "$(DATA_TAG)_bt_$${RUNID}"

eqflat:
	./scripts/eqflat.sh "$(DATA_TAG)"

# ----------------------------
# Healthchecks
# ----------------------------
tag-now:
	@echo "DATA_TAG=coinbase_live_$$(date -u +%Y%m%d_%H%M%S)"

health:
	$(COMPOSE) run --rm $(RUN_ENV) trade python -m files.main_healthcheck \
	  --exchange "$(DATA_TAG)" --symbol BTC_USD --timeframe 5m \
	  --step-ms 300000 --tail 250 --recent-k 12 \
	  --max-recent-gap 1 \
	  --cadence-grace-bars 12 \
	  --max-bad-recent 2 \
	  --max-staleness-ms 900000 \
	  --max-raw-staleness-ms 1800000

health_strict:
	$(COMPOSE) run --rm $(RUN_ENV) trade python -m files.main_healthcheck \
	  --exchange "$(DATA_TAG)" --symbol BTC_USD --timeframe 5m \
	  --step-ms 300000 --tail 250 --recent-k 12 \
	  --max-recent-gap 0 \
	  --cadence-grace-bars 0 \
	  --max-bad-recent 0 \
	  --max-staleness-ms 900000 \
	  --max-raw-staleness-ms 900000

status:
	@echo "== services in compose =="; \
	$(COMPOSE) config --services; \
	echo; \
	echo "== running containers =="; \
	$(COMPOSE) ps; \
	echo; \
	echo "== useful commands =="; \
	echo "  make jupyter-logs    # logs for trade (tooling)"; \
	echo "  make live-logs       # logs for paper (live loop)"; \
	echo "  make live-restart    # restart paper"; \
	echo "  make live-down       # stop paper"; \
	echo "  make down            # stop everything"

