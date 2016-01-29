
"""
The ziffect.matchers module, filled with convenient testtools matchers for use
with ziffect.
"""

from testtools.matchers import Not, Is


def Provides(interface):
    """
    Matches if interface is provided by the matchee.
    """
    return Not(Is(None))
