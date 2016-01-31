
import re
import testtools.run
import StringIO


def cleanup(lines):
    result = []
    hashes = {}

    def get_print_addr(match):
        addr = match.group(0)
        if addr not in hashes:
            hashes[addr] = '0x7fff%04d' % len(hashes.keys())
        return hashes[addr]

    def clean_filename(match):
        file = match.group(1)
        sp = 'site-packages'
        if sp in file:
            newfile = file.split(sp)[-1][1:]
        else:
            newfile = '<interactive-shell>'
        return 'File "%s"' % newfile

    for line in lines.splitlines():
        line = re.sub(r'0x[0-9a-f]*', get_print_addr, line)
        line = re.sub(r'File "([^"]*)"', clean_filename, line)
        result.append(line)

    return '\n'.join(result)


def run_test(test_case):
    output = StringIO.StringIO()
    loader = testtools.run.defaultTestLoader
    tests = loader.loadTestsFromTestCase(test_case)
    runner = testtools.run.TestToolsTestRunner(stdout=output)
    results = runner.run(tests)

    badness = None

    if results.failures:
        test_case, desc = results.failures[0]
        badness = 'FAILURE({})\n{}'.format(
            test_case._testMethodName,
            cleanup(desc)
        )
    elif results.errors:
        test_case, desc = results.errors[0]
        badness = 'ERROR({})\n{}'.format(
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
