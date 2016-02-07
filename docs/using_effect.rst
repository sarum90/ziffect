Coding with effect
==================

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
  from ziffect.doc import (
    run_test, DB, InMemoryDB, LATEST, DBStatus, DBResponse, rev_render, uuid4,
    seed
  )
  seed(1)


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

  from effect import TypeDispatcher, sync_performer

  class GetIntent(object):
    def __init__(self, doc_id, rev=LATEST):
      self.doc_id = doc_id
      self.rev = rev


  def get_performer_generator(db):
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
    def update(dispatcher, intent):
      intent.rev += 1
      return db.put(intent.doc_id, intent.rev, intent.doc)
    return update
      

  def db_dispatcher(db):
    return TypeDispatcher({
      GetIntent: sync_performer(get_performer_generator(db)),
      UpdateIntent: sync_performer(update_performer_generator(db)),
    })

Okay, so now we have the ``Effect`` -ive building blocks that we can use to
create our implementation:

.. testcode:: effect_implementation

  from effect import Effect
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

  from effect import (
    sync_perform, ComposedDispatcher, base_dispatcher
  )

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

.. Comment to end vim thinking this is bold text*

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
        repr(self.doc)
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
  AssertionError: Not all intents were performed: [GetIntent<LATEST, f456150c-d4ba-5b09-a3fc-7ce3a7dbe905>, UpdateIntent<1, f456150c-d4ba-5b09-a3fc-7ce3a7dbe905, {'a': 6, 'test': 'doc2'}>]
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

In response to some of the fears about using mocks, lets utilize an
``InMemoryDB`` fake and a ``NetoworkErrorDB`` fake in the next implementation.
This will force our tests to actually test in the performers in conjunction
with the other code. We are still using ``perform_sequence`` to inject the
fakes in a mock-like manner mind you.

.. testcode:: effect_implementation

  class NetworkErrorDB(object):
    def get(self, doc_id, rev=LATEST):
      return DBResponse(status=DBStatus.NETWORK_ERROR)

    def put(self, doc_id, rev, doc):
      return DBResponse(status=DBStatus.NETWORK_ERROR)

  class DBExecuteNetworkErrorTests(TestCase):

    def test_network_error(self):
      doc_id = uuid4()

      db = InMemoryDB()
      update_performer = update_performer_generator(db)
      get_performer = get_performer_generator(db)

      bad_db = NetworkErrorDB()
      bad_update_performer = update_performer_generator(bad_db)
      bad_get_performer = get_performer_generator(bad_db)

      db.put(doc_id, 0, {"test": "doc", "a": 1})
      doc_1 = {"test": "doc", "a": 1}
      doc_1_u = {"test": "doc", "a": 2}
      seq = [
        (GetIntent(doc_id), lambda i: bad_get_performer(None, i)),

        (GetIntent(doc_id), lambda i: get_performer(None, i)),

        (UpdateIntent(doc_id, 0, doc_1_u),
         lambda i: bad_update_performer(None, i)),

        (UpdateIntent(doc_id, 0, doc_1_u),
         lambda i: update_performer(None, i)),
      ]
      perform_sequence(seq, execute_function(
          doc_id, lambda x: dict(x, a=x.get("a", 0) + 1)
        )
      )

Test Failure:

.. doctest:: effect_implementation

  >>> run_test(DBExecuteNetworkErrorTests)
  ERROR(test_network_error)
  Traceback (most recent call last):
    File "<interactive-shell>", line 36, in test_network_error
    File "effect/testing.py", line 115, in perform_sequence
      return sync_perform(dispatcher, eff)
    File "effect/_sync.py", line 34, in sync_perform
      six.reraise(*errors[0])
    File "effect/_base.py", line 78, in guard
      return (False, f(*args, **kwargs))
    File "effect/do.py", line 120, in <lambda>
      return val.on(success=lambda r: _do(r, generator, False),
    File "effect/do.py", line 100, in _do
      val = generator.send(result)
    File "<interactive-shell>", line 6, in execute_function
    File "<interactive-shell>", line 36, in <lambda>
  AttributeError: 'NoneType' object has no attribute 'get'
  ...

.. Comment to end vim thinking this is bold text*

The ``NETWORK_ERROR`` on the get is causing issues...

.. testcode:: effect_implementation

  @do
  def execute_function(doc_id, pure_function):
    done = False
    while not done:
      original_doc = None
      while original_doc is None:
        original_doc = yield Effect(GetIntent(doc_id=doc_id))
        if original_doc.status == DBStatus.NETWORK_ERROR:
          original_doc = None
      new_doc = pure_function(original_doc.doc)
      update_result = yield Effect(
        UpdateIntent(doc_id, original_doc.rev, new_doc))
      done = (update_result.status == DBStatus.OK)

Run the test again:

.. doctest:: effect_implementation

  >>> run_test(DBExecuteNetworkErrorTests)
  FAILURE(test_network_error)
  Traceback (most recent call last):
    File "<interactive-shell>", line 36, in test_network_error
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
    File "<interactive-shell>", line 7, in execute_function
    File "effect/_base.py", line 150, in _perform
      performer = dispatcher(effect.intent)
    File "effect/testing.py", line 108, in dispatcher
      intent, fmt_log()))
  AssertionError: Performer not found: GetIntent<LATEST, 9515f7cf-8e34-c0f0-49ab-ddee515684b5>! Log follows:
  {{{
  sequence: GetIntent<LATEST, 9515f7cf-8e34-c0f0-49ab-ddee515684b5>
  sequence: GetIntent<LATEST, 9515f7cf-8e34-c0f0-49ab-ddee515684b5>
  sequence: UpdateIntent<1, 9515f7cf-8e34-c0f0-49ab-ddee515684b5, {'a': 2, 'test': 'doc'}>
  NOT FOUND: GetIntent<LATEST, 9515f7cf-8e34-c0f0-49ab-ddee515684b5>
  NEXT EXPECTED: UpdateIntent<0, 9515f7cf-8e34-c0f0-49ab-ddee515684b5, {'a': 2, 'test': 'doc'}>
  }}}
  ...

.. Comment to end vim thinking this is bold text*


The ``NETWORK_ERROR`` on the update is causing issues...

.. testcode:: effect_implementation

  @do
  def execute_function(doc_id, pure_function):
    done = False
    while not done:
      original_doc = None
      get_intent = GetIntent(doc_id=doc_id)
      while original_doc is None:
        original_doc = yield Effect(get_intent)
        if original_doc.status == DBStatus.NETWORK_ERROR:
          original_doc = None
      new_doc = pure_function(original_doc.doc)
      update_result = None
      update_intent = UpdateIntent(doc_id, original_doc.rev, new_doc)
      while update_result is None:
        update_result = yield Effect(update_intent)
        if update_result.status == DBStatus.NETWORK_ERROR:
          update_result = None
      done = (update_result.status == DBStatus.OK)

.. doctest:: effect_implementation

  >>> run_test(DBExecuteNetworkErrorTests)
  FAILURE(test_network_error)
  Traceback (most recent call last):
    File "<interactive-shell>", line 36, in test_network_error
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
    File "<interactive-shell>", line 15, in execute_function
    File "effect/_base.py", line 150, in _perform
      performer = dispatcher(effect.intent)
    File "effect/testing.py", line 108, in dispatcher
      intent, fmt_log()))
  AssertionError: Performer not found: UpdateIntent<1, c2d99fe7-48e7-9846-a601-ce405b5baedf, {'a': 2, 'test': 'doc'}>! Log follows:
  {{{
  sequence: GetIntent<LATEST, c2d99fe7-48e7-9846-a601-ce405b5baedf>
  sequence: GetIntent<LATEST, c2d99fe7-48e7-9846-a601-ce405b5baedf>
  sequence: UpdateIntent<1, c2d99fe7-48e7-9846-a601-ce405b5baedf, {'a': 2, 'test': 'doc'}>
  NOT FOUND: UpdateIntent<1, c2d99fe7-48e7-9846-a601-ce405b5baedf, {'a': 2, 'test': 'doc'}>
  NEXT EXPECTED: UpdateIntent<0, c2d99fe7-48e7-9846-a601-ce405b5baedf, {'a': 2, 'test': 'doc'}>
  }}}
  ...

.. Comment to end vim thinking this is bold text*

For those of you who are familiar with ``Effect``, you probably noticed pretty
early in this post what the error is about. My implementation of the
``update_performer`` modifies the intent that is passed in when it is called.
Specifically it increments the revision of the intent in place before passing
it to the underlying call to ``db.put``. With this implementation of how we
handle NETWORK_ERRORS we are re-using the same intent with the next performance
of update. The second run of ``update`` is unaware that the first one already
incremented ``rev``, so it is incremented a second time. This is the source of
our bug.

Effect recommends against mutating intents, but there is not any mechanism that
enforces it. Luckily, depending on your code it might be sort of rare to re-use
intents. If you do happen to re-use intents though, and you have not been
diligent about never mutating them, you might be vulnerable to some pretty
pesky bugs to track down.

The quick fix is simply not to modify intent in the function:

.. testcode:: effect_implementation

  def update_performer_generator(db):
    def update(dispatcher, intent):
      return db.put(intent.doc_id, intent.rev + 1, intent.doc)
    return update

.. doctest:: effect_implementation

  >>> run_test(DBExecuteNetworkErrorTests)
  [OK]


This for now pretty much wraps up my implementation using pure ``Effect``, but
there is one last observation I'd like to make:

TypeDispatchers are just classes
--------------------------------

Look at db_dispatcher:

.. testcode:: effect_implementation

  def db_dispatcher(db):
    return TypeDispatcher({
      GetIntent: sync_performer(get_performer_generator(db)),
      UpdateIntent: sync_performer(update_performer_generator(db)),
    })

This is a chunk of python that describes what functions to execute when a
certain identifier (type of intent) occurs. At some later point during the
program some values will be passed to one of the code chucks associated with
one of the identifiers.

It is sort of a funny way of describing it, but to me this describes a class
definition. The intents are bundles of arguments, the type of the intents are
the names of the methods, and the ``TypeDispatcher`` instance represents an
object that is an instance of that type.

Think about attempting to create a ``TypeDispatcher`` that can perform the same
effects as the objects returned by ``db_dispatcher``, but rather than
performing db interactions just writes an object to a file or reads an object
from a file:

.. testcode:: effect_implementation

  _FILEPATH = '/tmp/datastore'
  
  def _get_stored_obj():
    return json.load(open(_FILEPATH, "r"))
  
  def _store_obj(obj):
    return json.dump(obj, open(_FILEPATH, "w"))
  
  def file_update_performer(intent):
    file_store = _get_stored_obj()
    obj_revs = file_store.get(intent.doc_id, [])
    if len(obj_revs) != intent.rev:
      return DBResponse(status=DBStatus.CONFLICT)
    file_store[doc_id] = obj_revs
    obj_revs.push(intent.doc)
    _store_obj(file_store)
  
  def file_get_performer(dispatcher, intent):
    file_store = _get_stored_obj()
    if intent.rev < LATEST:
      return DBResponse(status=DBStatus.BAD_REQUEST)
    try:
      return DBResponse(
        status=DBStatus.OK,
        rev=intent.rev,
        doc=file_store[intent.doc_id][intent.rev]
      )
    except KeyError:
      return DBResponse(
        status=DBStatus.NOT_FOUND
      )
    except IndexError:
      return DBResponse(
        status=DBStatus.NOT_FOUND
      )

  def file_dispatcher():
    return TypeDispatcher({
      GetIntent: sync_performer(file_get_performer),
      UpdateIntent: sync_performer(file_update_performer),
    })
 
This feels a lot like implementing another class that implements the same
interface. It is just writing performers for a specific intent types
(``GetIntent`` and ``UpdateIntent``) rather than writing methods with specific
names.

If you put a bunch of dispatchers together using a ``ComposedDispatcher`` it
is similar to subclassing, in that you are adding more performers to the same
namespace, just like adding more methods to the same class. There even is the
ability to overload since ComposedDispatchers prefer earlier dispatchers over
later dispatchers.
