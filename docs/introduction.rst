
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

.. testcode::
  
  from __future__ import print_function
  

.. testcode::

  import effect
  import ziffect



Doctest example:

.. doctest::

   >>> 4
   4

Test-Output example:

.. testcode::

   a = ziffect.argument(type=int)
   print(123)

This would output:

.. testoutput::

   123
