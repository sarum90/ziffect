

default: all

all: doc test

test: unittest doctest

unittest:
	nosetests --nocapture ziffect/tests/basic_usage.py

doctest:
	if [[ $$TRAVIS_PYTHON_VERSION != "3.2"  ]]; then cd docs/ && make doctest; fi

doc:
	cd docs/ && make html
