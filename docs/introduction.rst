
Introduction
============

Motivation
----------

The motivation for ``ziffect`` was an inner sensation that
`effect <https://effect.readthedocs.org/>`_ was slightly incomplete, and with the
help of `zope.interface <http://docs.zope.org/zope.interface/>`_ and
`pyrsistent <https://pyrsistent.readthedocs.org/>`_ it could be made a lot
better.

Coding with effect
------------------

Let's walk through an example to illustrate my grievances with the ``effect``
library. For starters, let's say we are using ``effect`` to interact with a
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

  import json
  import hashlib
  from uuid import UUID, uuid1
  from six import int2byte

  _seed = [1]

  def get_random():
    _seed[0] += 1
    h = hashlib.md5()
    h.update(b"ziffect")
    h.update(int2byte(_seed[0]))
    return h.digest()

  def uuid4():
    return UUID(bytes=get_random())

  from pyrsistent import PClass, field
  from six import text_type
  from ziffect.doc import run_test

  LATEST=-1

  def rev_render(rev):
    if rev == LATEST:
      return 'LATEST'
    return text_type(rev)

  class DBStatus(object):
    NOT_FOUND = u'NOT_FOUND'
    OK = u'OK'
    CONFLICT = u'CONFLICT'
    BAD_REQUEST = u'BAD_REQUEST'
    NETWORK_ERROR = u'NETWORK_ERROR'

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

We still don't technically have what we set out for, as this effect generator
only takes two arguments, not the underlying db. So we'll add one more
convenience function that we can play around with on the interpreter:

.. testcode:: effect_implementation

  def sync_execute_function(db, doc_id, function):
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

.. testsetup:: effect_implementation

  from testtools import TestCase

.. testcode:: effect_implementation

  from effect.testing import perform_sequence

  class DBExecuteFunctionTests(TestCase):

    def test_happy_case(self):
      doc_id = uuid4()
      doc_1 = {"test": "doc", "a": 1}
      doc_1_u = {"test": "doc", "a": 2}
      seq = [
        (GetIntent(doc_id),
          lambda _: DBResponse(status=DBStatus.OK, rev=0, doc=doc_1)),

        (UpdateIntent(doc_id, 0, doc_1_u),
          lambda _: DBResponse(status=DBStatus.OK)),
      ]
      perform_sequence(seq, execute_function(
          doc_id, lambda x: dict(x, a=x.get("a", 0) + 1)
        )
      )
    
    def test_sad_case(self):
      doc_id = uuid4()
      doc_1 = {"test": "doc", "a": 1}
      doc_1_u = {"test": "doc", "a": 2}
      doc_2 = {"test": "doc2", "a": 5}
      doc_2_u = {"test": "doc2", "a": 6}
      seq = [
        (GetIntent(doc_id),
          lambda _: DBResponse(status=DBStatus.OK, rev=0, doc=doc_1)),

        (UpdateIntent(doc_id, 0, doc_1_u),
          lambda _: DBResponse(status=DBStatus.CONFLICT)),

        (GetIntent(doc_id),
          lambda _: DBResponse(status=DBStatus.OK, rev=1, doc=doc_2)),

        (UpdateIntent(doc_id, 1, doc_2_u),
          lambda _: DBResponse(status=DBStatus.OK)),
      ]
      perform_sequence(seq, execute_function(
          doc_id, lambda x: dict(x, a=x.get("a", 0) + 1)
        )
      )

Now a few iterations of TDD:

.. doctest:: effect_implementation

  >>> run_test(DBExecuteFunctionTests)
  FAILURE(test_happy_case)
  Traceback (most recent call last):
    File "<interactive-shell>", line 17, in test_happy_case
    File "effect/testing.py", line 115, in perform_sequence
      return sync_perform(dispatcher, eff)
    File "effect/_sync.py", line 34, in sync_perform
      six.reraise(*errors[0])
    File "effect/_base.py", line 78, in guard
      return (False, f(*args, **kwargs))
    File "effect/do.py", line 121, in <lambda>
      error=lambda e: _do(e, generator, True))
    File "effect/do.py", line 98, in _do
      val = generator.throw(*result)
    File "<interactive-shell>", line 6, in execute_function
    File "effect/_base.py", line 150, in _perform
      performer = dispatcher(effect.intent)
    File "effect/testing.py", line 108, in dispatcher
      intent, fmt_log()))
  AssertionError: Performer not found: <GetIntent object at 0x7fff0000>! Log follows:
  {{{
  NOT FOUND: <GetIntent object at 0x7fff0000>
  NEXT EXPECTED: <GetIntent object at 0x7fff0001>
  }}}
  ...

First bug: Intents need to have valid ``__eq__`` implementations. Also let's give
them a ``__repr__`` that makes them slightly less hard to work with.

.. testcode:: effect_implementation

  class GetIntent(object):
    def __init__(self, doc_id, rev=LATEST):
      self.doc_id = doc_id
      self.rev = rev
  
    def __eq__(self, other):
      return (
        type(self) == type(other) and
        self.doc_id == other.doc_id and
        self.rev == other.rev
      )

    def __repr__(self):
      return 'GetIntent<%s, %s>' % (
        rev_render(self.rev), self.doc_id)


  class UpdateIntent(object):
    def __init__(self, doc_id, rev, doc):
      self.doc_id = doc_id
      self.rev = rev
      self.doc = doc

    def __eq__(self, other):
      return (
        type(self) == type(other) and
        self.doc_id == other.doc_id and
        self.rev == other.rev and
        self.doc == other.doc
      )

    def __repr__(self):
      return 'UpdateIntent<%s, %s, %s>' % (
        rev_render(self.rev),
        self.doc_id,
        json.dumps(self.doc, sort_keys=True)
      )

Rerun the tests:

.. doctest:: effect_implementation

  >>> run_test(DBExecuteFunctionTests)
  FAILURE(test_sad_case)
  Traceback (most recent call last):
    File "<interactive-shell>", line 41, in test_sad_case
    File "effect/testing.py", line 115, in perform_sequence
      return sync_perform(dispatcher, eff)
    File "effect/testing.py", line 463, in consume
      [x[0] for x in self.sequence]))
  AssertionError: Not all intents were performed: [GetIntent<LATEST, f456150c-d4ba-5b09-a3fc-7ce3a7dbe905>, UpdateIntent<1, f456150c-d4ba-5b09-a3fc-7ce3a7dbe905, {"a": 6, "test": "doc2"}>]
  ...


Cool, now that we have a failing test, lets improve our implementation to
handle the case where the DB was updated while we were running:

.. testcode:: effect_implementation

  @do
  def execute_function(doc_id, pure_function):
    done = False
    while not done:
      original_doc = yield Effect(GetIntent(doc_id=doc_id))
      new_doc = pure_function(original_doc.doc)
      update_result = yield Effect(
        UpdateIntent(doc_id, original_doc.rev, new_doc))
      done = (update_result.status == DBStatus.OK)

Rerun the tests:

.. doctest:: effect_implementation

  >>> run_test(DBExecuteFunctionTests)
  [OK]

Okay, so that all seems reasonable. This style of testing reminds me a lot of
mocks. I am creating a canned sequence of expected inputs and return values for
my dependencies, and running my code under test using this canned dependency.


.. admonition:: Aside
  :class: hint

  I'm sure you can search the internet for debates of mocks versus fakes and
  find out more about the issues that some people have with mocks. In my view,
  two of the best arguments against mocks are:

  - Does the mock sufficiently behave like a real implementation so that the
    test is meaningful? This is particularly pertinent in python, because
    something simple like, "your mock does not return the correct type of
    value" might mean that your unit test fails to catch a ``TypeError`` that
    will always happen with the real implementation. 
  - Mocks create tests that are tightly tied to the implementation of the code
    under test; if the implementation is changed, the test must also be
    modified.  Consider, for instance, if we add a 2nd GetIntent to the
    beginning of the implementation, it should not change the correctness, but
    the test would now fail without modification. Specifically the sequence
    that is passed to perform_sequence would need a second GetIntent call at
    the beginning of the sequence.

  Personally, I think mocks do have a place in unit tests like the one above.
  Specifically you are interfacing with an API that can return different values
  for the same inputs, and you need to force some external state change at a
  specific time in order to force the different inputs.

  There are other strategies to do similar testing, but as long as you have a
  solid, simple interface to mock, I believe that form of testing gets the most
  bang for your buck.

Let's build on our existing implementation. Let's say after using this code for
awhile we realize that the DB commands can also return a ``NETWORK_ERROR``.
We are going to take the simple policy of retrying any attempt that results in
a ``NETWORK_ERROR``. We are not going to bother with exponential back-off or
any other nice-to-have right now, just a dead simply retry.

.. admonition:: Aside
  :class: hint

  Assuming that ``NETWORK_ERRORS`` can happen before or after an operation is
  complete, this has some interesting ramifications. Our implementation of
  :func:`execute_function` will be an at-least-once implementation, where it
  guarantees that the function you specified will have occured at least once on
  the doc_id specified. A poorly timed ``NETWORK_ERROR`` after a successful
  update will cause our code to retry the update, get a conflict, and cycle
  through the code again.

Simple test:

  class DBExecuteNetworkErrorTests(TestCase):

    def test_netword_error(self):
      doc_id = uuid4()
      doc_1 = {"test": "doc", "a": 1}
      doc_1_u = {"test": "doc", "a": 2}
      seq = [
        (GetIntent(doc_id),
          lambda _: DBResponse(status=DBStatus.NETWORK_ERROR)),

        (GetIntent(doc_id),
          lambda _: DBResponse(status=DBStatus.OK, rev=0, doc=doc_1)),

        (UpdateIntent(doc_id, 0, doc_1_u),
          lambda _: DBResponse(status=DBStatus.NETWORK_ERROR)),

        (UpdateIntent(doc_id, 0, doc_1_u),
          lambda _: DBResponse(status=DBStatus.OK)),
      ]
      perform_sequence(seq, execute_function(
          doc_id, lambda x: dict(x, a=x.get("a", 0) + 1)
        )
      )

Test Failure:


.. There is another directive: .. testoutput:: if testinputs have outputs
