
Introduction
============

Motivation
----------

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

.. admonition:: Aside
  :class: hint

  Apologies for this rather long example, I just wanted to walk through a
  sufficiently complex scenario as a matter of proving to myself that this
  library adds value.

.. testsetup:: *
  
  from __future__ import print_function

  from uuid import uuid4
  from pyrsistent import PClass, field
  from six import text_type
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
    status = field(type=text_type)
    doc = field(initial=None)
    rev = field(type=[int, type(None)], initial=None)

    def __repr__(self):
      result = text_type(self.status)
      if self.rev is not None:
        result += " rev=" + text_type(self.rev)
      if self.doc:
        result += u" " + json.dumps(self.doc, sort_keys=True)
      return u'DB Response<' + text_type(result) + u'>'

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

.. doctest:: show_db_functionality

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
the document, and put it back in the database. If the ``put`` fails, then the
code should get the latest version of the document, execute the pure function
on the latest version of the document, attempt to ``put`` it again, and repeat
until it succeeds.

For good measure, this code can return the final version of the document.

So let's take a stab at implementing this piece of code. We are using effect,
so I guess that means we want to put ``db.get`` and ``db.put`` behind intents
and performers, and then we want to create a function that returns an "effect
generator" that can be performed by a dispatcher.

.. admonition:: Aside
  :class: hint
  
  I'm still pretty new to ``effect``, and playing around with how to do
  good design in this paradigm. You may notice this in my tenative design
  desisions. If you have any recommendations on how I could do it better, tell
  me on github as an issue filed against
  `ziffect <https://github.com/sarum90/ziffect/issues>`_.

.. testcode:: effect_implementation

  from effect import Effect, sync_performer, TypeDispatcher

  class GetIntent(object):
    def __init__(self, doc_id, rev=LATEST):
      self.doc_id = doc_id
      self.rev = rev


  def get_performer_generator(db):
    @sync_performer
    def get(dispatcher, intent):
      return db.get(intent.doc_id, intent.rev)
    return get


  class UpdateIntent(object):
    def __init__(self, doc_id, rev, doc):
      """
      Slightly different API that the DB gives us, because we need to update a
      document below rather than just put a new doc into the DB.

      :param doc_id: The document id of the document to put in the database.
      :param rev: The last revision gotten from the database for the document.
        This update will put revision rev + 1 into the db.
      :param doc: The new document to send to the server.
      """
      self.doc_id = doc_id
      self.rev = rev
      self.doc = doc


  def update_performer_generator(db):
    @sync_performer
    def update(dispatcher, intent):
      intent.rev += 1
      return db.put(intent.doc_id, intent.rev, intent.doc)
    return update
      

  def db_dispatcher(db):
    return TypeDispatcher({
      GetIntent: get_performer_generator(db),
      UpdateIntent: update_performer_generator(db),
    })

Okay, so now we have the ``Effect`` -ive building blocks that we can use to
create our implementation:

.. testcode:: effect_implementation

  from effect import sync_perform, ComposedDispatcher, base_dispatcher
  from effect.do import do

  @do
  def execute_function(doc_id, pure_function):
    result = yield Effect(GetIntent(doc_id=doc_id))
    new_doc = pure_function(result.doc)
    yield Effect(UpdateIntent(doc_id, result.rev, new_doc))


  def sync_execute_function(db, doc_id, function):
    """
    Convenience wrapper to perform :func:`execute_function` on a database from
    an interactive terminal.
    """
    dispatcher = ComposedDispatcher([
      db_dispatcher(db),
      base_dispatcher
    ])
    sync_perform(
      dispatcher,
      execute_function(
        doc_id, function
      )
    )

The implementation of ``execute_function`` should fairly obviously have bugs,
but it's a good enough implementation that we can convince ourselves that the
happy case works:

.. doctest:: effect_implementation

  >>> db = DB()
  >>> doc_id = uuid4()
  >>> doc = {"cat": "mouse", "count": 10}
  >>> db.put(doc_id, 0, doc)
  DB Response<OK rev=0>

  >>> def increment(doc_id):
  ...     return sync_execute_function(
  ...        db,
  ...        doc_id,
  ...        lambda x: dict(x, count=x.get('count', 0) + 1)
  ...     )

  >>> increment(doc_id)
  >>> db.get(doc_id)
  DB Response<OK rev=1 {"cat": "mouse", "count": 11}>

  >>> increment(doc_id)
  >>> db.get(doc_id)
  DB Response<OK rev=2 {"cat": "mouse", "count": 12}>

  >>> increment(doc_id)
  >>> db.get(doc_id)
  DB Response<OK rev=3 {"cat": "mouse", "count": 13}>

In the interest of test driven development, at this point we want to write our
unit tests. They should fail, then we'll fix the implementation of
``execute_function``, write more unit tests, etc.



.. There is another directive: .. testoutput:: if testinputs have outputs
