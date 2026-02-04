COMPOSE = docker compose
COMPOSE_GPU = docker compose -f docker-compose.yml -f docker-compose.gpu.yml

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

correctness-gpu:
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm trade python -m files.main_correctness_check

logs:
	$(COMPOSE) logs -f

env:
	$(COMPOSE) run --rm trade python -c "from files.config import load_alpaca_config; load_alpaca_config(); print('Alpaca env OK')"

smoke:
	$(COMPOSE) run --rm trade python -m files.main_smoke

sanity:
	$(COMPOSE) run --rm trade python -m files.main_sanity_check

data-quality-gpu:
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm trade python -m files.main_data_quality_check

paper:
	$(COMPOSE) run --rm trade python -m files.main

# GPU versions (use the override file)
up-gpu:
	$(COMPOSE_GPU) up -d --build

smoke-gpu:
	$(COMPOSE_GPU) run --rm trade python -m files.main_smoke

sanity-gpu:
	$(COMPOSE_GPU) run --rm trade python -m files.main_sanity_check

paper-gpu:
	$(COMPOSE_GPU) run --rm trade python -m files.main

gpu-check:
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml exec trade nvidia-smi
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml exec trade \
	  python -c "import tensorflow as tf; print(tf.config.list_physical_devices('GPU'))"

features-check-gpu:
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm trade python -m files.main_features_check

state-check-gpu:
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm trade python -m files.main_state_check

report-gpu:
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm --env REPORT_DAYS_TAIL --env REPORT_EXCHANGE --env REPORT_SYMBOL --env REPORT_TIMEFRAME trade python -m files.utils.trade_report

report:
	docker compose -f docker-compose.yml run --rm trade python -m files.utils.trade_report

report-gpu2:
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm trade python -m files.utils.trade_report

report-decisions-gpu:
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm trade python -m files.utils.decision_report


# Usage:
#   RUNID=cmp_20260201 make backtest
#   RUNID=live_capture START_TS_MS=... END_TS_MS=... make backtest
#
# START_TS_MS / END_TS_MS are optional.
backtest:
	$(COMPOSE) run --rm trade python -m files.backtest \
	  --runid $${RUNID} \
	  $$( [ -n "$$START_TS_MS" ] && printf -- " --start-ts-ms %s" "$$START_TS_MS" ) \
	  $$( [ -n "$$END_TS_MS" ] && printf -- " --end-ts-ms %s" "$$END_TS_MS" )
