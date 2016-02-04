
from __future__ import print_function

import re
import testtools.run

import json
import hashlib
from uuid import UUID
from pyrsistent import PClass, field
from six import text_type, int2byte, StringIO


def cleanup(lines):
    result = []
    hashes = {}

    def get_print_addr(match):
        addr = match.group(0)
        if addr not in hashes:
            hashes[addr] = '0x7fff%04d' % len(hashes.keys())
        return hashes[addr]

    def clean_filename(line):
        regex = r'File "([^"]*)"'

        def _clean_filename(match):
            file = match.group(1)
            sp = 'site-packages'
            if sp in file:
                newfile = file.split(sp)[-1][1:]
            else:
                newfile = '<interactive-shell>'
            return 'File "%s"' % newfile

        line = re.sub(regex, _clean_filename, line)

        skip = 0
        if 'File "six' in line:
            skip = 2
        return line, skip

    skip = 0
    for line in lines.splitlines():
        if not skip:
            if '__exit__' in line:
                skip = 2
            elif 'fallback: Func(' in line:
                skip = 1
            else:
                line, skip = clean_filename(line)
        if skip > 0:
            skip -= 1
            continue
        line = re.sub(r'0x[0-9a-f]*', get_print_addr, line)
        line = line.replace(r'__builtin__.', r'')
        result.append(line)

    return '\n'.join(result)


def run_test(test_case):
    output = StringIO()
    loader = testtools.run.defaultTestLoader
    tests = loader.loadTestsFromTestCase(test_case)
    runner = testtools.run.TestToolsTestRunner(stdout=output)
    results = runner.run(tests)

    badness = None

    if results.failures:
        test_case, desc = results.failures[0]
        badness = 'FAILURE(%s)\n%s' % (
            test_case._testMethodName,
            cleanup(desc)
        )
    elif results.errors:
        test_case, desc = results.errors[0]
        badness = 'ERROR(%s)\n%s' % (
            test_case._testMethodName,
            cleanup(desc)
        )

    if badness:
        result = badness
        if results.testsRun > 0:
            result += '\n...'
    else:
        result = '[OK]'
    print(result)

_seed = [1]


def seed(val):
    _seed[0] = val


def get_random():
    _seed[0] += 1
    h = hashlib.md5()
    h.update(b"ziffect")
    h.update(int2byte(_seed[0]))
    return h.digest()


def uuid4():
    return UUID(bytes=get_random())


LATEST = -1


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
        return DBResponse(
            status=DBStatus.OK, rev=rev, doc=json.loads(docs[rev]))

    def put(self, doc_id, rev, doc):
        docs = self._data.get(doc_id, [])
        if rev != len(docs):
            return DBResponse(status=DBStatus.CONFLICT)
        docs.append(json.dumps(doc))
        self._data[doc_id] = docs
        return DBResponse(status=DBStatus.OK, rev=rev)

InMemoryDB = DB
