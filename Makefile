all: init test

init:
	pip install -r requirements.txt

test:
	pytest

.PHONY: all init test
