all: init test clean build

init:
	pip install -r requirements.txt

build:
	zip -r dist.zip *

test:
	python -m pytest

clean:
	rm -fr __pycache__ tests/__pycache__ dist.zip .pytest_cache/

.PHONY: all init test
