# Lệnh tắt (cần GNU make). Trên Windows có thể chạy trực tiếp các lệnh python tương ứng.
.PHONY: db init etl train score app test

db:
	docker compose up -d

init:
	python -m src.sql.init_db

etl:
	python -m src.etl.run_etl

train:
	python -m src.ml.late_risk --output-dir artifacts/models/late_risk/run_02

score:
	python -m src.dss.whatif --help

app:
	streamlit run src/app/app.py

test:
	pytest -q
