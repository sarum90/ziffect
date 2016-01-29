

default: all

all: doc test

test: unittest doctest

unittest:
	nosetests --nocapture ziffect/tests/basic_usage.py

doctest:
	cd docs/ && make doctest

doc:
	cd docs/ && make html
