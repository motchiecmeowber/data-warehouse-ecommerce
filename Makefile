# Lệnh tắt (cần GNU make). Trên Windows có thể chạy trực tiếp các lệnh python tương ứng.
.PHONY: db init etl olap train score app test

db:
	docker compose up -d

init:
	python -m src.sql.init_db

etl:
	python -m src.etl.run_etl

olap:
	python -m src.olap.build

train:
	python -m src.ml.train

score:
	python -m src.ml.predict

app:
	streamlit run src/app/app.py

test:
	pytest -q
