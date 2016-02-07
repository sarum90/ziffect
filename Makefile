

default: all

all: doc test

test: unittest doctest

unittest:
	nosetests --nocapture ziffect/tests/basic_usage.py

doctest:
ifeq ($(TRAVIS_PYTHON_VERSION),3.2)
	@echo "Not running doctests on python 3.2"
else
ifeq ($(TRAVIS_PYTHON_VERSION),pypy3)
	@echo "Not running doctests on pypy3"
else
	cd docs/ && make doctest
endif
endif

doc:
	cd docs/ && make html
