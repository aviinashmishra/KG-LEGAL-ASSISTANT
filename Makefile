.PHONY: install seed test run ui eval up down logs fmt

install:
	pip install -r requirements.txt

seed:
	python scripts/ingest_seed.py

test:
	pytest -q

run:
	uvicorn app.api.main:app --reload --port 8000

ui:
	streamlit run ui/streamlit_app.py

eval:
	python -m app.eval.ragas_eval

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f api
