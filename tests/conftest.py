# -*- coding: utf-8 -*-
"""
    :codeauthor: Pedro Algarvio (pedro@algarvio.me)

    tests.conftest
    ~~~~~~~~~~~~~~

    Prepare py.test for our test suite
'''
# pylint: disable=ungrouped-imports,wrong-import-position,redefined-outer-name,missing-docstring

# Import python libs
from __future__ import absolute_import, print_function, unicode_literals
import os
import sys
import stat
import shutil
import socket
import logging

TESTS_DIR = os.path.dirname(os.path.normpath(os.path.abspath(__file__)))
CODE_DIR = os.path.dirname(TESTS_DIR)

# Change to code checkout directory
os.chdir(CODE_DIR)

# Import test libs
from tests.support import paths  # pylint: disable=unused-import
from tests.support.runtests import RUNTIME_VARS

# Import pytest libs
import pytest
import _pytest.logging

# Import 3rd-party libs
import yaml
import psutil
from salt.ext import six

# Import salt libs
import salt.utils.files
import salt.utils.path
import salt.log.setup
import salt.log.mixins
import salt.utils.platform
from salt.utils.odict import OrderedDict
from salt.utils.immutabletypes import freeze

# Define the pytest plugins we rely on
# pylint: disable=invalid-name
pytest_plugins = ['tempdir', 'helpers_namespace', 'salt-from-filenames']

# Define where not to collect tests from
collect_ignore = ['setup.py']
# pylint: enable=invalid-name


# Patch PyTest logging handlers
# pylint: disable=protected-access,too-many-ancestors
class LogCaptureHandler(salt.log.mixins.ExcInfoOnLogLevelFormatMixIn,
                        _pytest.logging.LogCaptureHandler):
    '''
    Subclassing PyTest's LogCaptureHandler in order to add the
    exc_info_on_loglevel functionality.
    '''


_pytest.logging.LogCaptureHandler = LogCaptureHandler


class LiveLoggingStreamHandler(salt.log.mixins.ExcInfoOnLogLevelFormatMixIn,
                               _pytest.logging._LiveLoggingStreamHandler):
    '''
    Subclassing PyTest's LiveLoggingStreamHandler in order to add the
    exc_info_on_loglevel functionality.
    '''


_pytest.logging._LiveLoggingStreamHandler = LiveLoggingStreamHandler
# pylint: enable=protected-access,too-many-ancestors

# Reset logging root handlers
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)


log = logging.getLogger('salt.testsuite')


def pytest_tempdir_basename():
    """
    Return the temporary directory basename for the salt test suite.
    '''
    return 'salt-tests-tmpdir'


# ----- CLI Options Setup ------------------------------------------------------------------------------------------->
def pytest_addoption(parser):
    """
    register argparse-style options and ini-style config values.
    """
    parser.addoption(
        "--sysinfo",
        default=False,
        action="store_true",
        help="Print some system information.",
    )
    parser.addoption(
        '--transport',
        default='zeromq',
        choices=('zeromq', 'tcp'),
        help=('Select which transport to run the integration tests with, '
              'zeromq or tcp. Default: %default')
    )
    test_selection_group = parser.getgroup("Tests Selection")
    test_selection_group.addoption(
        "--ssh",
        "--ssh-tests",
        dest="ssh",
        action="store_true",
        default=False,
        help="Run salt-ssh tests. These tests will spin up a temporary "
        "SSH server on your machine. In certain environments, this "
        "may be insecure! Default: False",
    )
    test_selection_group.addoption(
        "--proxy",
        "--proxy-tests",
        dest="proxy",
        action="store_true",
        default=False,
        help="Run proxy tests",
    )
    test_selection_group.addoption(
        "--run-destructive",
        action="store_true",
        default=False,
        help="Run destructive tests. These tests can include adding "
        "or removing users from your system for example. "
        "Default: False",
    )
    test_selection_group.addoption(
        "--run-expensive",
        action="store_true",
        default=False,
        help="Run expensive tests. These tests usually involve costs "
        "like for example bootstrapping a cloud VM. "
        "Default: False",
    )
    output_options_group = parser.getgroup("Output Options")
    output_options_group.addoption(
        "--output-columns",
        default=80,
        type=int,
        help="Number of maximum columns to use on the output",
    )
    output_options_group.addoption(
        "--no-colors",
        "--no-colours",
        default=False,
        action="store_true",
        help="Disable colour printing.",
    )


# ----- Register Markers -------------------------------------------------------------------------------------------->
@pytest.mark.trylast
def pytest_configure(config):
    """
    called after command line options have been parsed
    and all plugins and initial conftest files been loaded.
    '''
    config.addinivalue_line('norecursedirs', os.path.join(CODE_DIR, 'templates'))
    config.addinivalue_line('norecursedirs', os.path.join(CODE_DIR, 'tests/support'))
    config.addinivalue_line(
        'filterwarnings',
        r'once:encoding is deprecated, Use raw=False instead\.:DeprecationWarning'
    )
    config.addinivalue_line(
        "markers",
        "destructive_test: Run destructive tests. These tests can include adding "
        "or removing users from your system for example.",
    )
    config.addinivalue_line(
        "markers", "skip_if_not_root: Skip if the current user is not `root`."
    )
    config.addinivalue_line(
        "markers",
        "skip_if_binaries_missing(*binaries, check_all=False, message=None): Skip if "
        "any of the passed binaries are not found in path. If 'check_all' is "
        "'True', then all binaries must be found.",
    )
    config.addinivalue_line(
        "markers",
        "requires_network(only_local_network=False): Skip if no networking is set up. "
        "If 'only_local_network' is 'True', only the local network is checked.",
    )
    # Make sure the test suite "knows" this is a pytest test run
    RUNTIME_VARS.PYTEST_SESSION = True

    # Provide a global timeout for each test(pytest-timeout).
    if config._env_timeout is None:
        # If no timeout is set, set it to the default timeout value
        # Right now, we set it to 5 minutes which is absurd, but let's see how it goes
        config._env_timeout = 5 * 60

    # We always want deferred timeouts. Ie, only take into account the test function time
    # to run, exclude fixture setup/teardown
    config._env_timeout_func_only = True
# <---- Register Markers ---------------------------------------------------------------------------------------------


# ----- PyTest Tweaks ----------------------------------------------------------------------------------------------->
def set_max_open_files_limits(min_soft=3072, min_hard=4096):

    # Get current limits
    if salt.utils.platform.is_windows():
        import win32file

        prev_hard = win32file._getmaxstdio()
        prev_soft = 512
    else:
        import resource

        prev_soft, prev_hard = resource.getrlimit(resource.RLIMIT_NOFILE)

    # Check minimum required limits
    set_limits = False
    if prev_soft < min_soft:
        soft = min_soft
        set_limits = True
    else:
        soft = prev_soft

    if prev_hard < min_hard:
        hard = min_hard
        set_limits = True
    else:
        hard = prev_hard

    # Increase limits
    if set_limits:
        log.debug(
            " * Max open files settings is too low (soft: %s, hard: %s) for running the tests. "
            "Trying to raise the limits to soft: %s, hard: %s",
            prev_soft,
            prev_hard,
            soft,
            hard,
        )
        try:
            if salt.utils.platform.is_windows():
                hard = 2048 if hard > 2048 else hard
                win32file._setmaxstdio(hard)
            else:
                resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))
        except Exception as err:  # pylint: disable=broad-except
            log.error(
                "Failed to raise the max open files settings -> %s. Please issue the following command "
                "on your console: 'ulimit -u %s'",
                err,
                soft,
            )
            exit(1)
    return soft, hard


def pytest_report_header():
    soft, hard = set_max_open_files_limits()
    return "max open files; soft: {}; hard: {}".format(soft, hard)


def pytest_runtest_logstart(nodeid):
    """
    signal the start of running a single test item.

    This hook will be called **before** :func:`pytest_runtest_setup`, :func:`pytest_runtest_call` and
    :func:`pytest_runtest_teardown` hooks.

    :param str nodeid: full id of the item
    :param location: a triple of ``(filename, linenum, testname)``
    """
    log.debug(">>>>> START >>>>> %s", nodeid)


def pytest_runtest_logfinish(nodeid):
    """
    signal the complete finish of running a single test item.

    This hook will be called **after** :func:`pytest_runtest_setup`, :func:`pytest_runtest_call` and
    :func:`pytest_runtest_teardown` hooks.

    :param str nodeid: full id of the item
    :param location: a triple of ``(filename, linenum, testname)``
    """
    log.debug("<<<<< END <<<<<<< %s", nodeid)


@pytest.hookimpl(hookwrapper=True, trylast=True)
def pytest_collection_modifyitems(config, items):
    """
    called after collection has been performed, may filter or re-order
    the items in-place.

    :param _pytest.main.Session session: the pytest session object
    :param _pytest.config.Config config: pytest config object
    :param List[_pytest.nodes.Item] items: list of item objects
    """
    # Let PyTest or other plugins handle the initial collection
    yield
    groups_collection_modifyitems(config, items)

    log.warning("Mofifying collected tests to keep track of fixture usage")
    for item in items:
        for fixture in item.fixturenames:
            if fixture not in item._fixtureinfo.name2fixturedefs:
                continue
            for fixturedef in item._fixtureinfo.name2fixturedefs[fixture]:
                if fixturedef.scope == "function":
                    continue
                try:
                    node_ids = fixturedef.node_ids
                except AttributeError:
                    node_ids = fixturedef.node_ids = set()
                node_ids.add(item.nodeid)
                try:
                    fixturedef.finish.__wrapped__
                except AttributeError:
                    original_func = fixturedef.finish

                    def wrapper(func, fixturedef):
                        @wraps(func)
                        def wrapped(self, request):
                            try:
                                return self._finished
                            except AttributeError:
                                if self.node_ids:
                                    log.debug(
                                        "%s is still going to be used, not terminating it. "
                                        "Still in use on:\n%s",
                                        self,
                                        pprint.pformat(list(self.node_ids)),
                                    )
                                    return
                                log.debug("Finish called on %s", self)
                                try:
                                    return func(request)
                                finally:
                                    self._finished = True

                        return partial(wrapped, fixturedef)

                    fixturedef.finish = wrapper(fixturedef.finish, fixturedef)
                    try:
                        fixturedef.finish.__wrapped__
                    except AttributeError:
                        fixturedef.finish.__wrapped__ = original_func


@pytest.hookimpl(trylast=True, hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    """
    implements the runtest_setup/call/teardown protocol for
    the given test item, including capturing exceptions and calling
    reporting hooks.

    :arg item: test item for which the runtest protocol is performed.

    :arg nextitem: the scheduled-to-be-next test item (or None if this
                   is the end my friend).  This argument is passed on to
                   :py:func:`pytest_runtest_teardown`.

    :return boolean: True if no further hook implementations should be invoked.


    Stops at first non-None result, see :ref:`firstresult`
    """
    request = item._request
    used_fixture_defs = []
    for fixture in item.fixturenames:
        if fixture not in item._fixtureinfo.name2fixturedefs:
            continue
        for fixturedef in reversed(item._fixtureinfo.name2fixturedefs[fixture]):
            if fixturedef.scope == "function":
                continue
            used_fixture_defs.append(fixturedef)
    try:
        # Run the test
        yield
    finally:
        for fixturedef in used_fixture_defs:
            fixturedef.node_ids.remove(item.nodeid)
            if not fixturedef.node_ids:
                # This fixture is not used in any more test functions
                fixturedef.finish(request)
    del request
    del used_fixture_defs


def pytest_runtest_teardown(item, nextitem):
    """
    called after ``pytest_runtest_call``.

    :arg nextitem: the scheduled-to-be-next test item (None if no further
                   test item is scheduled).  This argument can be used to
                   perform exact teardowns, i.e. calling just enough finalizers
                   so that nextitem only needs to call setup-functions.
    """
    # PyTest doesn't reset the capturing log handler when done with it.
    # Reset it to free used memory and python objects
    # We currently have PyTest's log_print setting set to false, if it was
    # set to true, the call bellow would make PyTest not print any logs at all.
    item.catch_log_handler.reset()


# <---- PyTest Tweaks ------------------------------------------------------------------------------------------------


# ----- Test Setup -------------------------------------------------------------------------------------------------->
def _has_unittest_attr(item, attr):
    # XXX: This is a hack while we support both runtests.py and PyTest
    if hasattr(item.obj, attr):
        return True
    if item.cls and hasattr(item.cls, attr):
        return True
    if item.parent and hasattr(item.parent.obj, attr):
        return True
    return False


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    """
    Fixtures injection based on markers or test skips based on CLI arguments
    '''
    destructive_tests_marker = item.get_closest_marker('destructive_test')
    if destructive_tests_marker is not None:
        if item.config.getoption('--run-destructive') is False:
            pytest.skip('Destructive tests are disabled')
    os.environ['DESTRUCTIVE_TESTS'] = six.text_type(item.config.getoption('--run-destructive'))

    expensive_tests_marker = item.get_closest_marker('expensive_test')
    if expensive_tests_marker is not None:
        if item.config.getoption('--run-expensive') is False:
            pytest.skip('Expensive tests are disabled')
    os.environ['EXPENSIVE_TESTS'] = six.text_type(item.config.getoption('--run-expensive'))

    skip_if_not_root_marker = item.get_closest_marker('skip_if_not_root')
    if skip_if_not_root_marker is not None:
        if os.getuid() != 0:
            pytest.skip('You must be logged in as root to run this test')

    skip_if_binaries_missing_marker = item.get_closest_marker('skip_if_binaries_missing')
    if skip_if_binaries_missing_marker is not None:
        binaries = skip_if_binaries_missing_marker.args
        if len(binaries) == 1:
            if isinstance(binaries[0], (list, tuple, set, frozenset)):
                binaries = binaries[0]
        check_all = skip_if_binaries_missing_marker.kwargs.get("check_all", False)
        message = skip_if_binaries_missing_marker.kwargs.get("message", None)
        if check_all:
            for binary in binaries:
                if salt.utils.path.which(binary) is None:
                    item._skipped_by_mark = True
                    pytest.skip(
                        '{0}The "{1}" binary was not found'.format(
                            message and "{0}. ".format(message) or "", binary
                        )
                    )
        elif salt.utils.path.which_bin(binaries) is None:
            item._skipped_by_mark = True
            pytest.skip(
                "{0}None of the following binaries was found: {1}".format(
                    message and "{0}. ".format(message) or "", ", ".join(binaries)
                )
            )

    requires_network_marker = item.get_closest_marker('requires_network')
    if requires_network_marker is not None:
        only_local_network = requires_network_marker.kwargs.get(
            "only_local_network", False
        )
        has_local_network = False
        # First lets try if we have a local network. Inspired in verify_socket
        try:
            pubsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            retsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            pubsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            pubsock.bind(("", 18000))
            pubsock.close()
            retsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            retsock.bind(("", 18001))
            retsock.close()
            has_local_network = True
        except socket.error:
            # I wonder if we just have IPV6 support?
            try:
                pubsock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                retsock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                pubsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                pubsock.bind(("", 18000))
                pubsock.close()
                retsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                retsock.bind(("", 18001))
                retsock.close()
                has_local_network = True
            except socket.error:
                # Let's continue
                pass

        if only_local_network is True:
            if has_local_network is False:
                # Since we're only supposed to check local network, and no
                # local network was detected, skip the test
                item._skipped_by_mark = True
                pytest.skip("No local network was detected")

        # We are using the google.com DNS records as numerical IPs to avoid
        # DNS lookups which could greatly slow down this check
        for addr in (
            "173.194.41.198",
            "173.194.41.199",
            "173.194.41.200",
            "173.194.41.201",
            "173.194.41.206",
            "173.194.41.192",
            "173.194.41.193",
            "173.194.41.194",
            "173.194.41.195",
            "173.194.41.196",
            "173.194.41.197",
        ):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.25)
                sock.connect((addr, 80))
                sock.close()
                # We connected? Stop the loop
                break
            except socket.error:
                # Let's check the next IP
                continue
            else:
                item._skipped_by_mark = True
                pytest.skip("No internet network connection was detected")

    requires_salt_modules_marker = item.get_closest_marker("requires_salt_modules")
    if requires_salt_modules_marker is not None:
        required_salt_modules = requires_salt_modules_marker.args
        if len(required_salt_modules) == 1 and isinstance(
            required_salt_modules[0], (list, tuple, set)
        ):
            required_salt_modules = required_salt_modules[0]
        required_salt_modules = set(required_salt_modules)
        not_available_modules = check_required_sminion_attributes(
            "functions", required_salt_modules
        )

        if not_available_modules:
            item._skipped_by_mark = True
            if len(not_available_modules) == 1:
                pytest.skip(
                    "Salt module '{}' is not available".format(*not_available_modules)
                )
            pytest.skip(
                "Salt modules not available: {}".format(
                    ", ".join(not_available_modules)
                )
            )

    requires_salt_states_marker = item.get_closest_marker("requires_salt_states")
    if requires_salt_states_marker is not None:
        required_salt_states = requires_salt_states_marker.args
        if len(required_salt_states) == 1 and isinstance(
            required_salt_states[0], (list, tuple, set)
        ):
            required_salt_states = required_salt_states[0]
        required_salt_states = set(required_salt_states)
        not_available_states = check_required_sminion_attributes(
            "states", required_salt_states
        )

        if not_available_states:
            item._skipped_by_mark = True
            if len(not_available_states) == 1:
                pytest.skip(
                    "Salt state module '{}' is not available".format(
                        *not_available_states
                    )
                )
            pytest.skip(
                "Salt state modules not available: {}".format(
                    ", ".join(not_available_states)
                )
            )

    if salt.utils.platform.is_windows():
        if not item.fspath.fnmatch(os.path.join(CODE_DIR, "tests", "unit", "*")):
            # Unit tests are whitelisted on windows by default, so, we're only
            # after all other tests
            windows_whitelisted_marker = item.get_closest_marker("windows_whitelisted")
            if windows_whitelisted_marker is None:
                item._skipped_by_mark = True
                pytest.skip("Test is not whitelisted for Windows")


# <---- Test Setup ---------------------------------------------------------------------------------------------------


# ----- Automatic Markers Setup ------------------------------------------------------------------------------------->
def pytest_collection_modifyitems(items):
    '''
    Automatically add markers to tests based on directory layout
    '''
    for item in items:
        fspath = str(item.fspath)
        if '/integration/' in fspath:
            if 'default_session_daemons' not in item.fixturenames:
                item.fixturenames.append('default_session_daemons')
            item.add_marker(pytest.mark.integration)
            for kind in ('cli', 'client', 'cloud', 'fileserver', 'loader', 'minion', 'modules',
                         'netapi', 'output', 'reactor', 'renderers', 'runners', 'sdb', 'shell',
                         'ssh', 'states', 'utils', 'wheel'):
                if '/{0}/'.format(kind) in fspath:
                    item.add_marker(getattr(pytest.mark, kind))
                    break
        if '/unit/' in fspath:
            item.add_marker(pytest.mark.unit)
            for kind in ('acl', 'beacons', 'cli', 'cloud', 'config', 'grains', 'modules', 'netapi',
                         'output', 'pillar', 'renderers', 'runners', 'serializers', 'states',
                         'templates', 'transport', 'utils'):
                if '/{0}/'.format(kind) in fspath:
                    item.add_marker(getattr(pytest.mark, kind))
                    break
# <---- Automatic Markers Setup --------------------------------------------------------------------------------------


# ----- Pytest Helpers ---------------------------------------------------------------------------------------------->
if six.PY2:
    # backport mock_open from the python 3 unittest.mock library so that we can
    # mock read, readline, readlines, and file iteration properly

    file_spec = None

    def _iterate_read_data(read_data):
        # Helper for mock_open:
        # Retrieve lines from read_data via a generator so that separate calls to
        # readline, read, and readlines are properly interleaved
        data_as_list = ["{0}\n".format(l) for l in read_data.split("\n")]

        if data_as_list[-1] == "\n":
            # If the last line ended in a newline, the list comprehension will have an
            # extra entry that's just a newline.  Remove this.
            data_as_list = data_as_list[:-1]
        else:
            # If there wasn't an extra newline by itself, then the file being
            # emulated doesn't have a newline to end the last line  remove the
            # newline that our naive format() added
            data_as_list[-1] = data_as_list[-1][:-1]

        for line in data_as_list:
            yield line

    @pytest.helpers.mock.register
    def mock_open(mock=None, read_data=""):
        """
        A helper function to create a mock to replace the use of `open`. It works
        for `open` called directly or used as a context manager.

        The `mock` argument is the mock object to configure. If `None` (the
        default) then a `MagicMock` will be created for you, with the API limited
        to methods or attributes available on standard file handles.

        `read_data` is a string for the `read` methoddline`, and `readlines` of the
        file handle to return.  This is an empty string by default.
        """
        _mock = pytest.importorskip("mock", minversion="2.0.0")

        # pylint: disable=unused-argument
        def _readlines_side_effect(*args, **kwargs):
            if handle.readlines.return_value is not None:
                return handle.readlines.return_value
            return list(_data)

        def _read_side_effect(*args, **kwargs):
            if handle.read.return_value is not None:
                return handle.read.return_value
            return ''.join(_data)
        # pylint: enable=unused-argument

        def _readline_side_effect():
            if handle.readline.return_value is not None:
                while True:
                    yield handle.readline.return_value
            for line in _data:
                yield line

        global file_spec  # pylint: disable=global-statement
        if file_spec is None:
            file_spec = file  # pylint: disable=undefined-variable

        if mock is None:
            mock = _mock.MagicMock(name="open", spec=open)

        handle = _mock.MagicMock(spec=file_spec)
        handle.__enter__.return_value = handle

        _data = _iterate_read_data(read_data)

        handle.write.return_value = None
        handle.read.return_value = None
        handle.readline.return_value = None
        handle.readlines.return_value = None

        handle.read.side_effect = _read_side_effect
        handle.readline.side_effect = _readline_side_effect()
        handle.readlines.side_effect = _readlines_side_effect

        mock.return_value = handle
        return mock


else:

    @pytest.helpers.mock.register
    def mock_open(mock=None, read_data=""):
        _mock = pytest.importorskip("mock", minversion="2.0.0")
        return _mock.mock_open(mock=mock, read_data=read_data)


@pytest.helpers.register
@contextmanager
def temp_directory(name=None):
    if name is not None:
        directory_path = os.path.join(RUNTIME_VARS.TMP, name)
    else:
        directory_path = tempfile.mkdtemp(dir=RUNTIME_VARS.TMP)

    yield directory_path

    shutil.rmtree(directory_path, ignore_errors=True)


@pytest.helpers.register
@contextmanager
def temp_file(name, contents=None, directory=None, strip_first_newline=True):
    if directory is None:
        directory = RUNTIME_VARS.TMP

    file_path = os.path.join(directory, name)
    file_directory = os.path.dirname(file_path)
    if contents is not None:
        if contents:
            if contents.startswith("\n") and strip_first_newline:
                contents = contents[1:]
            file_contents = textwrap.dedent(contents)
        else:
            file_contents = contents

    try:
        if not os.path.isdir(file_directory):
            os.makedirs(file_directory)
        if contents is not None:
            with salt.utils.files.fopen(file_path, "w") as wfh:
                wfh.write(file_contents)

        yield file_path

    finally:
        try:
            os.unlink(file_path)
        except OSError:
            # Already deleted
            pass


@pytest.helpers.register
def temp_state_file(name, contents, saltenv="base", strip_first_newline=True):

    if saltenv == "base":
        directory = RUNTIME_VARS.TMP_STATE_TREE
    elif saltenv == "prod":
        directory = RUNTIME_VARS.TMP_PRODENV_STATE_TREE
    else:
        raise RuntimeError(
            '"saltenv" can only be "base" or "prod", not "{}"'.format(saltenv)
        )
    return temp_file(
        name, contents, directory=directory, strip_first_newline=strip_first_newline
    )


# <---- Pytest Helpers -----------------------------------------------------------------------------------------------


# ----- Fixtures Overrides ------------------------------------------------------------------------------------------>
# ----- Generate CLI Scripts ---------------------------------------------------------------------------------------->
@pytest.fixture(scope="session")
def cli_master_script_name():
    """
    Return the CLI script basename
    """
    return "cli_salt_master.py"


@pytest.fixture(scope="session")
def cli_minion_script_name():
    """
    Return the CLI script basename
    """
    return "cli_salt_minion.py"


@pytest.fixture(scope="session")
def cli_salt_script_name():
    """
    Return the CLI script basename
    """
    return "cli_salt.py"


@pytest.fixture(scope="session")
def cli_run_script_name():
    """
    Return the CLI script basename
    """
    return "cli_salt_run.py"


@pytest.fixture(scope="session")
def cli_key_script_name():
    """
    Return the CLI script basename
    """
    return "cli_salt_key.py"


@pytest.fixture(scope="session")
def cli_call_script_name():
    """
    Return the CLI script basename
    """
    return "cli_salt_call.py"


@pytest.fixture(scope="session")
def cli_syndic_script_name():
    """
    Return the CLI script basename
    """
    return "cli_salt_syndic.py"


@pytest.fixture(scope="session")
def cli_ssh_script_name():
    """
    Return the CLI script basename
    """
    return "cli_salt_ssh.py"


@pytest.fixture(scope="session")
def cli_proxy_script_name():
    """
    Return the CLI script basename
    '''
    return 'cli_salt_ssh'


@pytest.fixture(scope='session')
def cli_bin_dir(tempdir,
                request,
                python_executable_path,
                cli_master_script_name,
                cli_minion_script_name,
                cli_salt_script_name,
                cli_call_script_name,
                cli_key_script_name,
                cli_run_script_name,
                cli_ssh_script_name,
                cli_syndic_script_name):
    '''
    Return the path to the CLI script directory to use
    """
    tmp_cli_scripts_dir = tempdir.join("cli-scrips-bin")
    # Make sure we re-write the scripts every time we start the tests
    shutil.rmtree(tmp_cli_scripts_dir.strpath, ignore_errors=True)
    tmp_cli_scripts_dir.ensure(dir=True)
    cli_bin_dir_path = tmp_cli_scripts_dir.strpath

    # Now that we have the CLI directory created, lets generate the required CLI scripts to run salt's test suite
    script_templates = {
        'salt': [
            'from salt.scripts import salt_main\n',
            'if __name__ == \'__main__\':\n'
            '    salt_main()'
        ],
        'salt-api': [
            'import salt.cli\n',
            'def main():\n',
            '    sapi = salt.cli.SaltAPI()',
            '    sapi.run()\n',
            'if __name__ == \'__main__\':',
            '    main()'
        ],
        'common': [
            'from salt.scripts import salt_{0}\n',
            'if __name__ == \'__main__\':\n',
            '    salt_{0}()'
        ]
    }

    for script_name in (cli_master_script_name,
                        cli_minion_script_name,
                        cli_call_script_name,
                        cli_key_script_name,
                        cli_run_script_name,
                        cli_salt_script_name,
                        cli_ssh_script_name,
                        cli_syndic_script_name):
        original_script_name = script_name.split('cli_')[-1].replace('_', '-')
        script_path = os.path.join(cli_bin_dir_path, script_name)

        if not os.path.isfile(script_path):
            log.info('Generating %s', script_path)

            with salt.utils.files.fopen(script_path, 'w') as sfh:
                script_template = script_templates.get(original_script_name, None)
                if script_template is None:
                    script_template = script_templates.get('common', None)
                if script_template is None:
                    raise RuntimeError(
                        'Salt\'s test suite does not know how to handle the "{0}" script'.format(
                            original_script_name
                        )
                    )
                sfh.write(
                    '#!{0}\n\n'.format(python_executable_path) +
                    'import sys\n' +
                    'CODE_DIR="{0}"\n'.format(request.config.startdir.realpath().strpath) +
                    'if CODE_DIR not in sys.path:\n' +
                    '    sys.path.insert(0, CODE_DIR)\n\n' +
                    '\n'.join(script_template).format(original_script_name.replace('salt-', ''))
                )
            fst = os.stat(script_path)
            os.chmod(script_path, fst.st_mode | stat.S_IEXEC)

    # Return the CLI bin dir value
    return cli_bin_dir_path


# <---- Generate CLI Scripts -----------------------------------------------------------------------------------------


# ----- Salt Configuration ------------------------------------------------------------------------------------------>
@pytest.fixture(scope='session')
def session_master_of_masters_id():
    '''
    Returns the master of masters id
    '''
    return 'syndic_master'


@pytest.fixture(scope='session')
def session_master_id():
    '''
    Returns the session scoped master id
    '''
    return 'master'


@pytest.fixture(scope='session')
def session_minion_id():
    '''
    Returns the session scoped minion id
    '''
    return 'minion'


@pytest.fixture(scope='session')
def session_secondary_minion_id():
    '''
    Returns the session scoped secondary minion id
    '''
    return 'sub_minion'


@pytest.fixture(scope='session')
def session_syndic_id():
    '''
    Returns the session scoped syndic id
    '''
    return 'syndic'


@pytest.fixture(scope='session')
def salt_fail_hard():
    '''
    Return the salt fail hard value
    '''
    return True


@pytest.fixture(scope='session')
def session_master_default_options(request, session_root_dir):
    with salt.utils.files.fopen(os.path.join(RUNTIME_VARS.CONF_DIR, 'master')) as rfh:
        opts = yaml.load(rfh.read())

        tests_known_hosts_file = session_root_dir.join('salt_ssh_known_hosts').strpath
        with salt.utils.files.fopen(tests_known_hosts_file, 'w') as known_hosts:
            known_hosts.write('')

        opts['known_hosts_file'] = tests_known_hosts_file
        opts['syndic_master'] = 'localhost'
        opts['transport'] = request.config.getoption('--transport')

        return opts


@pytest.fixture(scope='session')
def session_master_config_overrides(session_root_dir):
    if salt.utils.platform.is_windows():
        ext_pillar = {'cmd_yaml': 'type {0}'.format(os.path.join(RUNTIME_VARS.FILES, 'ext.yaml'))}
    else:
        ext_pillar = {'cmd_yaml': 'cat {0}'.format(os.path.join(RUNTIME_VARS.FILES, 'ext.yaml'))}

    # We need to copy the extension modules into the new master root_dir or
    # it will be prefixed by it
    extension_modules_path = session_root_dir.join('extension_modules').strpath
    if not os.path.exists(extension_modules_path):
        shutil.copytree(
            os.path.join(
                RUNTIME_VARS.FILES, 'extension_modules'
            ),
            extension_modules_path
        )

    # Copy the autosign_file to the new  master root_dir
    autosign_file_path = session_root_dir.join('autosign_file').strpath
    shutil.copyfile(
        os.path.join(RUNTIME_VARS.FILES, 'autosign_file'),
        autosign_file_path
    )
    # all read, only owner write
    autosign_file_permissions = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH | stat.S_IWUSR
    os.chmod(autosign_file_path, autosign_file_permissions)

    return {
        'ext_pillar': [ext_pillar],
        'extension_modules': extension_modules_path,
        'file_roots': {
            'base': [
                os.path.join(RUNTIME_VARS.FILES, 'file', 'base'),
            ],
            # Alternate root to test __env__ choices
            'prod': [
                os.path.join(RUNTIME_VARS.FILES, 'file', 'prod'),
            ]
        },
        'pillar_roots': {
            'base': [
                os.path.join(RUNTIME_VARS.FILES, 'pillar', 'base'),
            ]
        },
        'reactor': [
            {
                'salt/minion/*/start': [
                    os.path.join(RUNTIME_VARS.FILES, 'reactor-sync-minion.sls')
                ],
            }
        ]
    }


@pytest.fixture(scope='session')
def session_minion_default_options(request, session_root_dir):
    with salt.utils.files.fopen(os.path.join(RUNTIME_VARS.CONF_DIR, 'minion')) as rfh:
        opts = yaml.load(rfh.read())

        opts['hosts.file'] = session_root_dir.join('hosts').strpath
        opts['aliases.file'] = session_root_dir.join('aliases').strpath
        opts['transport'] = request.config.getoption('--transport')

        return opts


@pytest.fixture(scope='session')
def session_minion_config_overrides():
    return {
        'file_roots': {
            'base': [
                os.path.join(RUNTIME_VARS.FILES, 'file', 'base'),
            ],
            # Alternate root to test __env__ choices
            'prod': [
                os.path.join(RUNTIME_VARS.FILES, 'file', 'prod'),
            ]
        },
        'pillar_roots': {
            'base': [
                os.path.join(RUNTIME_VARS.FILES, 'pillar', 'base'),
            ]
        },
    }


@pytest.fixture(scope='session')
def session_secondary_minion_default_options(request, session_root_dir):
    with salt.utils.files.fopen(os.path.join(RUNTIME_VARS.CONF_DIR, 'sub_minion')) as rfh:
        opts = yaml.load(rfh.read())

        opts['hosts.file'] = session_root_dir.join('hosts').strpath
        opts['aliases.file'] = session_root_dir.join('aliases').strpath
        opts['transport'] = request.config.getoption('--transport')

        return opts


@pytest.fixture(scope='session')
def session_master_of_masters_default_options(request, session_root_dir):
    with salt.utils.files.fopen(os.path.join(RUNTIME_VARS.CONF_DIR, 'syndic_master')) as rfh:
        opts = yaml.load(rfh.read())

        opts['hosts.file'] = session_root_dir.join('hosts').strpath
        opts['aliases.file'] = session_root_dir.join('aliases').strpath
        opts['transport'] = request.config.getoption('--transport')

        return opts


@pytest.fixture(scope='session')
def session_master_of_masters_config_overrides(session_master_of_masters_root_dir):
    if salt.utils.platform.is_windows():
        ext_pillar = {'cmd_yaml': 'type {0}'.format(os.path.join(RUNTIME_VARS.FILES, 'ext.yaml'))}
    else:
        ext_pillar = {'cmd_yaml': 'cat {0}'.format(os.path.join(RUNTIME_VARS.FILES, 'ext.yaml'))}

    # We need to copy the extension modules into the new master root_dir or
    # it will be prefixed by it
    extension_modules_path = session_master_of_masters_root_dir.join('extension_modules').strpath
    if not os.path.exists(extension_modules_path):
        shutil.copytree(
            os.path.join(
                RUNTIME_VARS.FILES, 'extension_modules'
            ),
            extension_modules_path
        )

    # Copy the autosign_file to the new  master root_dir
    autosign_file_path = session_master_of_masters_root_dir.join('autosign_file').strpath
    shutil.copyfile(
        os.path.join(RUNTIME_VARS.FILES, 'autosign_file'),
        autosign_file_path
    )
    # all read, only owner write
    autosign_file_permissions = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH | stat.S_IWUSR
    os.chmod(autosign_file_path, autosign_file_permissions)

    return {
        'ext_pillar': [ext_pillar],
        'extension_modules': extension_modules_path,
        'file_roots': {
            'base': [
                os.path.join(RUNTIME_VARS.FILES, 'file', 'base'),
            ],
            # Alternate root to test __env__ choices
            'prod': [
                os.path.join(RUNTIME_VARS.FILES, 'file', 'prod'),
            ]
        },
        'pillar_roots': {
            'base': [
                os.path.join(RUNTIME_VARS.FILES, 'pillar', 'base'),
            ]
        },
    }


@pytest.fixture(scope='session')
def session_syndic_master_default_options(request, session_root_dir):
    with salt.utils.files.fopen(os.path.join(RUNTIME_VARS.CONF_DIR, 'syndic_master')) as rfh:
        opts = yaml.load(rfh.read())

        opts['hosts.file'] = session_root_dir.join('hosts').strpath
        opts['aliases.file'] = session_root_dir.join('aliases').strpath
        opts['transport'] = request.config.getoption('--transport')

        return opts


@pytest.fixture(scope='session')
def session_syndic_default_options(request, session_root_dir):
    with salt.utils.files.fopen(os.path.join(RUNTIME_VARS.CONF_DIR, 'syndic')) as rfh:
        opts = yaml.load(rfh.read())

        opts['hosts.file'] = session_root_dir.join('hosts').strpath
        opts['aliases.file'] = session_root_dir.join('aliases').strpath
        opts['transport'] = request.config.getoption('--transport')

        return opts


@pytest.fixture(scope='session', autouse=True)
def bridge_pytest_and_runtests(session_root_dir,
                               session_conf_dir,
                               session_secondary_conf_dir,
                               session_syndic_conf_dir,
                               session_master_of_masters_conf_dir,
                               session_base_env_pillar_tree_root_dir,
                               session_base_env_state_tree_root_dir,
                               session_prod_env_state_tree_root_dir,
                               session_master_config,
                               session_minion_config,
                               session_secondary_minion_config,
                               session_master_of_masters_config,
                               session_syndic_config):

    # Make sure unittest2 classes know their paths
    RUNTIME_VARS.TMP = RUNTIME_VARS.SYS_TMP_DIR = session_root_dir.realpath().strpath
    RUNTIME_VARS.TMP_CONF_DIR = session_conf_dir.realpath().strpath
    RUNTIME_VARS.TMP_SUB_MINION_CONF_DIR = session_secondary_conf_dir.realpath().strpath
    RUNTIME_VARS.TMP_SYNDIC_MASTER_CONF_DIR = session_master_of_masters_conf_dir.realpath().strpath
    RUNTIME_VARS.TMP_SYNDIC_MINION_CONF_DIR = session_syndic_conf_dir.realpath().strpath
    RUNTIME_VARS.TMP_PILLAR_TREE = session_base_env_pillar_tree_root_dir.realpath().strpath
    RUNTIME_VARS.TMP_STATE_TREE = session_base_env_state_tree_root_dir.realpath().strpath
    RUNTIME_VARS.TMP_PRODENV_STATE_TREE = session_prod_env_state_tree_root_dir.realpath().strpath

    # Make sure unittest2 uses the pytest generated configuration
    RUNTIME_VARS.RUNTIME_CONFIGS['master'] = freeze(session_master_config)
    RUNTIME_VARS.RUNTIME_CONFIGS['minion'] = freeze(session_minion_config)
    RUNTIME_VARS.RUNTIME_CONFIGS['sub_minion'] = freeze(session_secondary_minion_config)
    RUNTIME_VARS.RUNTIME_CONFIGS['syndic_master'] = freeze(session_master_of_masters_config)
    RUNTIME_VARS.RUNTIME_CONFIGS['syndic'] = freeze(session_syndic_config)
    RUNTIME_VARS.RUNTIME_CONFIGS['client_config'] = freeze(session_master_config)

    # Copy configuration files and directories which are not automatically generated
    for entry in os.listdir(RUNTIME_VARS.CONF_DIR):
        if entry in ('master', 'minion', 'sub_minion', 'syndic', 'syndic_master', 'proxy'):
            # These have runtime computed values and are handled by pytest-salt fixtures
            continue
        entry_path = os.path.join(RUNTIME_VARS.CONF_DIR, entry)
        if os.path.isfile(entry_path):
            shutil.copy(
                entry_path,
                os.path.join(RUNTIME_VARS.TMP_CONF_DIR, entry)
            )
        elif os.path.isdir(entry_path):
            shutil.copytree(
                entry_path,
                os.path.join(RUNTIME_VARS.TMP_CONF_DIR, entry)
            )
# <---- Salt Configuration -------------------------------------------------------------------------------------------

    # Copy configuration files and directories which are not automatically generated
    for entry in os.listdir(RUNTIME_VARS.CONF_DIR):
        if entry in (
            "master",
            "minion",
            "sub_minion",
            "syndic",
            "syndic_master",
            "proxy",
        ):
            # These have runtime computed values and are handled by pytest-salt fixtures
            continue
        entry_path = os.path.join(RUNTIME_VARS.CONF_DIR, entry)
        if os.path.isfile(entry_path):
            shutil.copy(entry_path, os.path.join(RUNTIME_VARS.TMP_CONF_DIR, entry))
        elif os.path.isdir(entry_path):
            shutil.copytree(entry_path, os.path.join(RUNTIME_VARS.TMP_CONF_DIR, entry))


# <---- Salt Configuration -------------------------------------------------------------------------------------------
# <---- Fixtures Overrides -------------------------------------------------------------------------------------------
# ----- Custom Fixtures Definitions --------------------------------------------------------------------------------->
# pylint: disable=unused-argument
@pytest.fixture(scope='session')
def session_salt_syndic(request, session_salt_master_of_masters, session_salt_syndic):
    request.session.stats_processes.update(OrderedDict((
        ('Salt Syndic Master', psutil.Process(session_salt_master_of_masters.pid)),
        ('       Salt Syndic', psutil.Process(session_salt_syndic.pid)),
    )).items())
    return session_salt_syndic


@pytest.fixture(scope='session')
def default_session_daemons(request,
                            log_server,
                            salt_log_port,
                            engines_dir,
                            log_handlers_dir,
                            session_salt_master,
                            session_salt_minion,
                            session_secondary_salt_minion,
                            ):

    request.session.stats_processes.update(OrderedDict((
        ('       Salt Master', psutil.Process(session_salt_master.pid)),
        ('       Salt Minion', psutil.Process(session_salt_minion.pid)),
        ('   Salt Sub Minion', psutil.Process(session_secondary_salt_minion.pid)),
    )).items())
# pylint: enable=unused-argument
# <---- Custom Fixtures Definitions ----------------------------------------------------------------------------------
