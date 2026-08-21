.PHONY: install doctor test plan produce run product clean

install:
	pip install -r requirements.txt

doctor:
	python -m eve.cli doctor

test:
	python -m pytest tests -q

plan:
	python -m eve.cli plan --days 7

produce:
	python -m eve.cli produce --limit 2

run:
	python -m eve.cli run

product:
	python -m eve.cli product

clean:
	rm -rf output/videos output/images output/audio .pytest_cache
	find . -name __pycache__ -type d -exec rm -rf {} +
