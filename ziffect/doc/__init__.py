
import re
import testtools.run
from six import StringIO


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
            if 'fallback: Func(' in line:
                skip = 1
        if not skip:
            line, skip = clean_filename(line)
        if skip > 0:
            skip -= 1
            continue
        line = re.sub(r'0x[0-9a-f]*', get_print_addr, line)
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
