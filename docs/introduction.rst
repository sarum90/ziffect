
Introduction
------------

The motivation for ``ziffect`` was an inner sensation that
`effect <https://effect.readthedocs.org/>`_ was slightly incomplete, and with the
help of `zope.interface <http://docs.zope.org/zope.interface/>`_ and
`pyrsistent <https://pyrsistent.readthedocs.org/>`_ it could be made a lot
better.

Using Effect and Limitations
----------------------------

Let's walk through an example to illustrate my grievances with the ``effect``
library. For starters, lets say we are using ``effect`` to interact with a
database. Reading values from and writing values to a database are certainly
operations that have side-effects, so we believe this to be a good candidate
use case for our new toy.

Apologies for this rather long example, I just wanted to walk through a
sufficiently complex scenario as a matter of proving to myself that this
library adds value.

.. testsetup:: *
  
  from __future__ import print_function

  from uuid import uuid4
  from pyrsistent import PClass, field
  import json

  LATEST=-1

  class DBStatus(object):
    NOT_FOUND = u'NOT_FOUND'
    OK = u'OK'
    CONFLICT = u'CONFLICT'
    BAD_REQUEST = u'BAD_REQUEST'
    # Unused, but is next logical step:
    # NETWORK_ERROR = u'NETWORK_ERROR'

  class DBResponse(PClass):
    status = field(type=unicode)
    doc = field(initial=None)
    rev = field(type=[int, type(None)], initial=None)

    def __repr__(self):
      result = unicode(self.status)
      if self.rev is not None:
        result += " rev={}".format(self.rev)
      if self.doc:
        result += " {}".format(json.dumps(self.doc))
      return 'DB Response<{}>'.format(result)

  class DB(object):
    def __init__(self):
      self._data = {}

    def get(self, doc_id, rev=LATEST):
      docs = self._data.get(doc_id)
      if not docs:
        return DBResponse(status=DBStatus.NOT_FOUND)
      if rev >= len(docs):
        return DBResponse(status=DBStatus.NOT_FOUND)
      if rev < LATEST:
        return DBResponse(status=DBStatus.BAD_REQUEST)
      if rev < 0:
        rev = len(docs) + rev
      return DBResponse(status=DBStatus.OK, rev=rev, doc=json.loads(docs[rev]))

    def put(self, doc_id, rev, doc):
      docs = self._data.get(doc_id, [])
      if rev != len(docs):
        return DBResponse(status=DBStatus.CONFLICT)
      docs.append(json.dumps(doc))
      self._data[doc_id] = docs
      return DBResponse(status=DBStatus.OK, rev=rev)

For sake of example I will assume we are using a simple revision-based document
store (perhaps a wrapper on CouchDB). This document store has a simple
synchronous python API that consists of merely ``db.get(doc_id, rev=LATEST)``
and ``db.put(doc_id, rev, doc)``. As this is a fictional API, rather than
giving a full spec, I will demonstrate how it works with a simple demo of
functionality:

.. doctest:: show_db

  >>> # Make a new db.
  >>> db = DB()
  >>> # Create an id for a doc we'll work with.
  >>> my_id = uuid4()

  >>> # Getting a doc that doesn't exist is an error:
  >>> db.get(my_id)  
  DB Response<NOT_FOUND>

  >>> # Putting revision 0 for a doc that doesn't exist succeeds:
  >>> db.put(my_id, 0, {'cat': 0})
  DB Response<OK rev=0>

  >>> # `get`ing a doc gets the latest version:
  >>> db.get(my_id)
  DB Response<OK rev=0 {"cat": 0}>

  >>> # Attempting to put a document at existant revision is an error:
  >>> db.put(my_id, 0, {'cat': 12})
  DB Response<CONFLICT>

  >>> # Instead `put` it at the next revision:
  >>> db.put(my_id, 1, {'cat': 12})
  DB Response<OK rev=1>

  >>> # `get`ing a doc gets the latest version:
  >>> db.get(my_id)
  DB Response<OK rev=1 {"cat": 12}>

  >>> # But old revisions can still be gotten:
  >>> db.get(my_id, 0)
  DB Response<OK rev=0 {"cat": 0}>

..  Potentially add the following if needed to show something cool: Note that
    these are all database calls, and any of them could also end in a
    ``NETWORK_ERROR`` in which case we would not know what state the database
    is in.

Using this system, we will try to implement a piece of code that will execute a
change on a document in the database. This code should take as inputs:

- A ``DB`` instance where the document is stored.
- The ``doc_id`` of the document that is to be changed within the database.
- A pure function to execute on the document.

The code will get the document from the database, execute the pure function on
the document, and put it back in the database. If the PUT fails

For good measure, this code can return the final version of the document.


Doctest example:

.. doctest::

   >>> 4
   4

Test-Output example:

.. testcode::

   import ziffect
   a = ziffect.argument(type=int)
   print(123)

This would output:

.. testoutput::

   123
