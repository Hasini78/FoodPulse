.PHONY: setup run-backend run-frontend run-etl test

setup:
	python -m venv .venv
	.venv/bin/pip install -r backend/requirements.txt || .venv/Scripts/pip install -r backend/requirements.txt
	cd frontend && npm install
	@echo "Setup complete. Copy .env.example to .env if needed."

run-backend:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

run-frontend:
	cd frontend && npm run dev

run-etl:
	python etl/load/seed.py --csv-only

test:
	cd backend && pytest -q || true
	@echo "Frontend tests not configured yet."
