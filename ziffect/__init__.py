
"""
The ziffect module.
"""

from __future__ import unicode_literals

from effect import TypeDispatcher, Effect, sync_performer
from pyrsistent import PClass, field, PClassMeta
from six import add_metaclass, iteritems
from funcsigs import signature

__all__ = [
    'interface',
    'effects',
    'argument'
]


class argument(PClass):
    """
    Argument type

    TODO(mewert): fill the rest of this in.
    """
    type = field(type=type)


def _make_intent_from_args(args):
    """
    Create an intent type for a given set of arguments.

    :param args: a dict with keys as the names of arguments and values as
        :class:`argument`s.

    :returns: A new type that can hold all of the data to call a function that
        has the given arguments.
    """
    class _Intent(PClass):
        pass

    for name, arg in iteritems(args):
        setattr(_Intent, name, field(type=arg.type))

    _PIntent = add_metaclass(PClassMeta)(_Intent)

    return _PIntent


def _iterate_methods(interface):
    """
    A generator to iterate over the methods of an interface.

    :param interface: A ziffect interface.

    :yields: names of methods.
    """
    for operator_name in dir(interface):
        if not operator_name.startswith('_'):
            yield operator_name


def _get_method_argspecs(interface):
    """
    A generator to get the argspecs of methods on an interface.

    :param interface: The ziffect interface to inspect.

    :yields: tuples of method name and dictionaries that map name of
        argument to :class:`argument` instances.
    """
    for method_name in _iterate_methods(interface):
        method = getattr(interface, method_name)
        sig = signature(method)
        args = dict(
            (name, arg.default)
            for name, arg in iteritems(sig.parameters)
        )
        yield method_name, args


def _make_intents(argspecs):
    """
    Constructs intents for each of the argspecs passed in.

    :param argspecs: A dict with keys as method names, and values as
        dicts that map name of argument to :class:`argument` instances.

    :return: dict that maps method_name to intent class.
    """
    return dict(
     (method_name, _make_intent_from_args(args))
     for method_name, args in iteritems(argspecs)
    )


def _make_effect_method(intent):
    """
    Turn an intent into a method that creates an effect.

    :param intent: The class for the intent.

    :returns Effect: An effect that describes the given intent.
    """
    def _method(self, **kwargs):
        return Effect(intent(**kwargs))
    return _method


def _make_effects(intents):
    """
    Creates a class that has methods that generate effects for the given
    intents.

    :param intents: dict mapping names of intents to their classes.

    :returns: A new class with method names equal to the keys of the input.
        Each method on this class will generate an Effect for use with the
        Effect library.
    """
    class _Effects(object):
        pass

    for method_name, intent in iteritems(intents):
        method = _make_effect_method(intent)
        setattr(_Effects, method_name, method)

    return _Effects()


def interface(wrapped_class):
    """
    Class decorator to wrap ziffect interfaces.

    :param wrapped_class: The class to wrap.

    :returns: The newly created wrapped class.
    """
    wrapped_class._ziffect_argspecs = dict(
        (key, value)
        for key, value in _get_method_argspecs(wrapped_class)
    )
    wrapped_class._ziffect_intents = _make_intents(
        wrapped_class._ziffect_argspecs)
    wrapped_class._ziffect_effects = _make_effects(
        wrapped_class._ziffect_intents)
    return wrapped_class


def effects(interface):
    """
    Method to get an object that implements interface by just returning effects
    for each method call.

    :param interface: The interface for which to create a provider.

    :returns: A class with method names equal to the method names of the
        interface. Each method on this class will generate an Effect for use
        with the Effect library.
    """
    return interface._ziffect_effects


def implements(interface):
    """
    Class decorator to indicate that wrapped_class implements the interface.

    :param interface: The interface that is implemented by the class.

    :returns: decorator for the wrapped class.
    """
    def _implements_decorator(wrapped_class):
        return wrapped_class
    return _implements_decorator


def _make_performer(method, arg_keys):
    """
    Constructs a performer for that calls a specific method. This involves
    unpacking the intent into keyword arguments for the method.

    Note that this presently does not pass the dispatcher down to the
    underlying method. Thus, ziffect interface implementations presently cannot
    perform other effects that have side effects.

    :param method: The underlying method to call. Should be a method bound to
        an object that provides a ziffect interface.
    :param arg_keys: Iterable of strings that are both the keyword arguments of
        the method and the names of the attributes of the intent.

    :returns: An Effect performer that calls method with the arguments in the
        intent.
    """
    @sync_performer
    def _perform(dispatcher, intent):
        args = dict(
            (k, getattr(intent, k))
            for k in arg_keys
        )
        return method(**args)
    return _perform


def dispatcher(interface_map):
    """
    Creates a dispatcher for a number of interfaces.

    :param interface_map: A map from ziffect interface to a provider of the
        interface.

    :returns: An Effect dispatcher that will use the passed in interfaces to
        perform Effects that have been generated from the
        ``ziffect.effect(interface).method()`` implementation.
    """
    typemap = {}
    for interface, provider in iteritems(interface_map):
        intents = interface._ziffect_intents
        argspecs = interface._ziffect_argspecs
        for method_name in _iterate_methods(interface):
            method = getattr(provider, method_name)
            intent = intents[method_name]
            typemap[intent] = _make_performer(method,
                                              argspecs[method_name].keys())
    return TypeDispatcher(typemap)
