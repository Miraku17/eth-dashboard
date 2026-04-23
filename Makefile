.PHONY: up down logs migrate test backend-test frontend-build lint

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

migrate:
	docker compose exec api alembic upgrade head

backend-test:
	cd backend && .venv/bin/pytest -v

frontend-build:
	cd frontend && npm run build

lint:
	cd backend && .venv/bin/ruff check .
	cd frontend && npm run lint

test: backend-test
