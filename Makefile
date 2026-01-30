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

