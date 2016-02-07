Coding with ziffect
===================

The ``ziffect`` takes the idea of ``TypeDispatchers`` as a core part of the
design. Similar to zope interfaces, you start coding with ziffect by specifying
an interface that you will implement. It also builds upon ``pyrsistent``
``PClass`` s, and thus adds type-checking at intent creation time.

.. testsetup:: *
  
  from __future__ import print_function
  import json
  from ziffect.doc import (
    run_test, DB, InMemoryDB, LATEST, DBStatus, DBResponse, rev_render, uuid4,
    seed,
  )
  _my_uuid = uuid4()
  seed(0xbf)

.. testcode:: ziffect_implementation

  from uuid import UUID
  from six import text_type
  import ziffect

  @ziffect.interface
  class DBInterface(object):

    def get(doc_id=ziffect.argument(type=UUID),
            rev=ziffect.argument(type=int, default=LATEST)):
      pass

    def update(doc_id=ziffect.argument(type=UUID),
               rev=ziffect.argument(type=int),
               doc=ziffect.argument(type=dict)):
      pass

This specifies the interface to the DB that we intend to implement. So when we
write performers, we just write a class that implements the interface:

.. testcode:: ziffect_implementation

  @ziffect.implements(DBInterface)
  class ZiffectDB(object):
    def __init__(self, db):
      """
      :param db: The underlying db to make calls to.
      """
      self.db = db

    def get(self, doc_id, rev):
      return self.db.get(doc_id, rev)

    def update(self, doc_id, rev, doc):
      rev += 1
      return self.db.put(doc_id, rev, doc)


Note that this bit of code is supposed to encompass both the ``TypeDispatcher``
as well as the performers from earlier.

Then when we go to actually implement our function, we need to be able to
create effects representing the methods on our interface. To do that we use
``ziffect.effects``. When you pass ziffect.effects a ``ziffect`` interface it
returns an object that has all the same methods as the interface and generates
effects representing the intent of having those methods called on some other
implementation:

.. testcode:: ziffect_implementation

  from effect.do import do

  @do
  def execute_function(doc_id, pure_function):
    db_effects = ziffect.effects(DBInterface)
    result = yield db_effects.get(doc_id=doc_id)
    new_doc = pure_function(result.doc)
    yield db_effects.update(doc_id=doc_id,
                            rev=result.rev,
                            doc=new_doc)

Again we need a nice little wrapper if we are going to attempt to use this tool
interactively. Note that ``ziffect`` also can create dispatchers for you. The
``ziffect`` dispatcher is created using ``ziffect.dispatcher``. It takes a dict
that maps ``ziffect`` interfaces to objects that provide that interface. This
is effectively choosing the implementation of the interface that will be used
to perform effects created from ``ziffect.effects`` -style effect generators.

.. testcode:: ziffect_implementation

  from effect import (
    sync_perform, ComposedDispatcher, base_dispatcher
  )

  def sync_execute_function(db, doc_id, function):
    dispatcher = ComposedDispatcher([
      ziffect.dispatcher({
        DBInterface: ZiffectDB(db)
      }),
      base_dispatcher
    ])
    sync_perform(
      dispatcher,
      execute_function(
        doc_id, function
      )
    )

Running the same interactive test that we ran on our effect implementation:

.. doctest:: ziffect_implementation

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

Again the happy case works right out of the box. Once again we'll continue with
test-driven development. For starters, I'll demonstrate directly how we can use
the same tools we used when testing ``effect`` to test with ``ziffect`` .

.. testsetup:: ziffect_implementation

  from testtools import TestCase

.. testcode:: ziffect_implementation

  from effect.testing import perform_sequence

  class DBExecuteFunctionTests(TestCase):

    def test_happy_case(self):
      db_intents = ziffect.intents(DBInterface)
      doc_id = uuid4()
      doc_1 = {"test": "doc", "a": 1}
      doc_1_u = {"test": "doc", "a": 2}
      seq = [
        (db_intents.get(doc_id=doc_id),
         lambda _: DBResponse(status=DBStatus.OK, rev=0, doc=doc_1)),

        (db_intents.update(doc_id=doc_id,
                           rev=0,
                           doc=doc_1_u),
         lambda _: DBResponse(status=DBStatus.OK)),
      ]
      perform_sequence(seq, execute_function(
          doc_id, lambda x: dict(x, a=x.get("a", 0) + 1)
        )
      )
    
    def test_sad_case(self):
      db_intents = ziffect.intents(DBInterface)
      doc_id = uuid4()
      doc_1 = {"test": "doc", "a": 1}
      doc_1_u = {"test": "doc", "a": 2}
      doc_2 = {"test": "doc2", "a": 5}
      doc_2_u = {"test": "doc2", "a": 6}
      seq = [
        (db_intents.get(doc_id=doc_id),
          lambda _: DBResponse(status=DBStatus.OK, rev=0, doc=doc_1)),

        (db_intents.update(doc_id=doc_id, rev=0, doc=doc_1_u),
          lambda _: DBResponse(status=DBStatus.CONFLICT)),

        (db_intents.get(doc_id=doc_id),
          lambda _: DBResponse(status=DBStatus.OK, rev=1, doc=doc_2)),

        (db_intents.update(doc_id=doc_id, rev=1, doc=doc_2_u),
          lambda _: DBResponse(status=DBStatus.OK)),
      ]
      perform_sequence(seq, execute_function(
          doc_id, lambda x: dict(x, a=x.get("a", 0) + 1)
        )
      )

Now to run the test and fix as needed:

.. doctest:: ziffect_implementation

  >>> run_test(DBExecuteFunctionTests)
  FAILURE(test_sad_case)
  Traceback (most recent call last):
    File "<interactive-shell>", line 45, in test_sad_case
    File "effect/testing.py", line 115, in perform_sequence
      return sync_perform(dispatcher, eff)
    File "effect/testing.py", line 463, in consume
      [x[0] for x in self.sequence]))
  AssertionError: Not all intents were performed: [_Intent(doc_id=UUID('3a80d1fb-b1b0-35b7-bd12-39ccdbbc9f69'), rev=-1), _Intent(doc={'a': 6, 'test': 'doc2'}, doc_id=UUID('3a80d1fb-b1b0-35b7-bd12-39ccdbbc9f69'), rev=1)]
  ...

We have the expected error of not doing a get in the case of receiving a
conflict notification.

.. admonition:: Aside
  :class: hint

  Obviously the fact that all of those intents are named ``_Intent`` is less than
  desireable. ``ziffect`` is a work in progress, and long term I hope to make
  all of the meta attributes (``__name__`` and the like) on the auto-generated
  intents much more usable.

Fixing the error by doing a full implementation:


.. testcode:: ziffect_implementation

  @do
  def execute_function(doc_id, pure_function):
    db_effects = ziffect.effects(DBInterface)
    done = False
    while not done:
      original = yield db_effects.get(doc_id=doc_id)
      new_doc = pure_function(original.doc)
      result = yield db_effects.update(doc_id=doc_id,
                                       rev=original.rev,
                                       doc=new_doc)
      done = (result.status == DBStatus.OK)


.. doctest:: ziffect_implementation

  >>> run_test(DBExecuteFunctionTests)
  [OK]

Okay, so already we have had a marginally easier time working with ``ziffect``.
We did not have to write quite as much boiler plate code defining intents and
creating dispatchers, and the intents that ``ziffect`` created for us had
reasonable ``__repr__`` and ``__eq__`` implementations so we did not have to
deal with that ourselves.

For completeness, we'll continue on with the addition of the ``NETWORK_ERROR``
retries as we have done previously.


.. testcode:: ziffect_implementation

  #@ziffect.implements(DBInterface)
  class NetworkErrorDB(object):
    def get(self, doc_id, rev=LATEST):
      return DBResponse(status=DBStatus.NETWORK_ERROR)

    def put(self, doc_id, rev, doc):
      return DBResponse(status=DBStatus.NETWORK_ERROR)


  class DBExecuteNetworkErrorTests(TestCase):

    def test_network_error(self):
      doc_id = uuid4()
      db_intents = ziffect.intents(DBInterface)

      db = InMemoryDB()
      bad_db = NetworkErrorDB()

      good_impl = ZiffectDB(db)
      bad_impl = ZiffectDB(bad_db)

      db.put(doc_id, 0, {"test": "doc", "a": 1})
      doc_1 = {"test": "doc", "a": 1}
      doc_1_u = {"test": "doc", "a": 2}
      seq = [
        (db_intents.get(doc_id=doc_id), bad_impl.get),

        (db_intents.get(doc_id=doc_id), good_impl.get),

        (db_intents.update(doc_id=doc_id, rev=0, doc=doc_1_u),
         bad_impl.update),

        (db_intents.update(doc_id=doc_id, rev=0, doc=doc_1_u),
         good_impl.update),
      ]
      ziffect.perform_sequence_destructed_args(
        seq, execute_function(
          doc_id, lambda x: dict(x, a=x.get("a", 0) + 1)
        )
      )

Note

.. doctest:: ziffect_implementation

  >>> run_test(DBExecuteNetworkErrorTests)
  ERROR(test_network_error)
  Traceback (most recent call last):
    File "<interactive-shell>", line 38, in test_network_error
    File "<interactive-shell>", line 294, in perform_sequence_destructed_args
      effect_generator)
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
    File "<interactive-shell>", line 7, in execute_function
    File "<interactive-shell>", line 38, in <lambda>
  AttributeError: 'NoneType' object has no attribute 'get'
  ...

.. Comment to end vim thinking this is bold text*

So we have to actually add the retries on ``NETWORK_ERROR`` s:

.. testcode:: ziffect_implementation

  @do
  def execute_function(doc_id, pure_function):
    db_effects = ziffect.effects(DBInterface)
    done = False
    while not done:
      original = None
      while original is None:
        original = yield db_effects.get(doc_id=doc_id)
        if original.status == DBStatus.NETWORK_ERROR:
          original = None
      new_doc = pure_function(original.doc)
      result = None
      while result is None:
        result = yield db_effects.update(doc_id=doc_id,
                                         rev=original.rev,
                                         doc=new_doc)
        if result.status == DBStatus.NETWORK_ERROR:
          result = None
      done = (result.status == DBStatus.OK)

And we've completed our implementation:

.. doctest:: ziffect_implementation

  >>> run_test(DBExecuteNetworkErrorTests)
  [OK]

Summary
-------

Hopefully, that example was sufficient to demonstrate the benifits of using
``ziffect`` instead of ``effect`` directly, although there certainly is some
room for criticism:

1. *Most of the benefits of ``ziffect`` come fro using ``pyrsistent`` to make
	 intents. If you just have a codebase-wide policy of using ``pyrsistent`` to
	 make intents, you would not have to add the dependency on ``ziffect``.* This
   is probably true, and it certainly is the case the ``ziffect`` has made some
   decisions in favor of ease-of-use over flexability.  Nonetheless, I think
   ``ziffect`` also comes with a model of code that is cleaner and easier to
   maintain long term. Specifically, sandboxing performers behind interfaces
   makes it easier to identify which performers concern a specific system of
   side effects, and provide a clear interface to fake out if you want a fake
   implementation for testing.

2. *``ziffect`` peformers do not get a ``dispatcher`` argument, how am I
   supposed to write performers that dispatch other ``Events``.* This is
   certainly true, ``ziffect`` does not allow for as flexible performers
   because it does not pass the dispatcher in.  I'm still trying to figure out
   how to think about the dispatcher argument, and processing ideas of what the
   API should look like.
   
   Sometimes ``dispatcher`` feels like dependency injection to me. For
   instance, if you are writing a performer and you want to ensure that
   something is logged before and after you do some operation, you might use
   the dispatcher that is handed in to dispatch some ``Log`` events. You just
   want to ensure the ``Log`` intent is handled, but the implementation is
   determined at runtime by what dispatcher you have.

   Other times, ``dispatcher`` is just providing an interface for performers
   that are schedulers. For instance, you could have an ``in_parallel`` intent,
   which would simply use the dispatcher to dispatch all of the events at once,
   and then aggregate the events to a single event before concluding the event
   they are performing. This feels subtly different than the other use of
   ``dispatcher`` to me.

   As I figure out how to reconcile these two uses of ``dispatcher`` and
   determine if they are fundamentally different or effectively the same, I'll
   be extending the ``ziffect`` API to support these performers.


Future Work
-----------

* Lots of error handling tests.  I'd like to add tests for common coding
  mistakes, and ensure the errors raised are actionable for the programmer.

* Actual integration with ``zope.interface``, presently the test matcher is a
  lie, and actually integrating with ``zope.interface`` would allow for the
  creation of proxy implementations.

* Utilities, like a function that takes a ``ziffect`` interface and a provider
  of that interface, and returns an implementation of that interface that logs
  before and after that function finishes.

* ``txziffect`` or equivalent.


