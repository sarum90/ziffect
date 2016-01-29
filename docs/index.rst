.. Ziffect documentation master file, created by
   sphinx-quickstart on Tue Jan 26 23:00:19 2016.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to Ziffect's documentation
===================================

Contents:

.. toctree::
   :maxdepth: 2

Indices and tables
===================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`


The Ziffect module
==================

.. testsetup:: *

   import ziffect
   import effect

Introduction
------------

The motivation for ``ziffect`` was an inner sensation that
`effect <https://effect.readthedocs.org/>`_ was slightly incomplete, and with the
help of `zope.interface <http://docs.zope.org/zope.interface/>`_ and
`pyrsistent <https://pyrsistent.readthedocs.org/>`_ it could be made a lot
better.

Using Effect and Limitations
----------------------------

The parrot module is a module about parrots.

Doctest example:

.. doctest::

   >>> effect.Effect(int)
  <Effect(intent=<type 'int'>, callbacks=[])>

Test-Output example:

.. testcode::

   effect.argument(type=int)

This would output:

.. testoutput::

   This parrot wouldn't voom if you put 3000 volts through it!

API
===

.. automodule:: ziffect
  :members:
