
from __future__ import unicode_literals

from testtools import TestCase
from testtools.matchers import Equals
from six import text_type
from effect import sync_perform

import ziffect
import ziffect.matchers


@ziffect.interface
class Utils(object):
    """
    Lets pretend we have a ``Utils`` interface.
    """

    def add(operator_a=ziffect.argument(type=int),
            operator_b=ziffect.argument(type=int)):
        """
        The add method does some sort of action on two ints.
        """
        pass

    def concat(operator_a=ziffect.argument(type=text_type),
               operator_b=ziffect.argument(type=text_type)):
        """
        The concat method does some sort of action on two text arguments.
        """
        pass


@ziffect.implements(Utils)
class RecordCallsUtils(object):
    """
    Implementation of Utils interface that
    """
    def __init__(self):
        self.calls = dict(
            add=[],
            concat=[]
        )

    def add(self, operator_a, operator_b):
        self.calls['add'].append((operator_a, operator_b))

    def concat(self, operator_a, operator_b):
        self.calls['concat'].append((operator_a, operator_b))


class BasicUsage(TestCase):
    """
    Tests for the simple use cases of this library.
    """

    def test_basic_usage(self):
        """
        Using an implementation of a ziffect interface that
        """
        utils_effects = ziffect.effects(Utils)
        my_call_logger = RecordCallsUtils()

        self.expectThat(my_call_logger, ziffect.matchers.Provides(Utils))

        dispatcher = ziffect.dispatcher({
            Utils: my_call_logger
        })

        sync_perform(
            dispatcher,
            utils_effects.add(operator_a=12, operator_b=23)
        )
        self.expectThat(
            my_call_logger.calls['add'], Equals([(12, 23)]))

        sync_perform(
            dispatcher,
            utils_effects.concat(operator_a='me', operator_b='ow')
        )
        self.expectThat(
            my_call_logger.calls['concat'], Equals([('me', 'ow')])
        )
