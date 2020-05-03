# -*- coding: utf-8 -*-

# Import python libs
from __future__ import absolute_import, print_function, unicode_literals

import logging
import re

import salt.utils.platform

# Import Salt Libs
import salt.utils.pycrypto

# Import Salt Testing Libs
from tests.support.unit import TestCase, skipIf

log = logging.getLogger(__name__)


class PycryptoTestCase(TestCase):
    """
    TestCase for salt.utils.pycrypto module
    """

    @skipIf(not salt.utils.pycrypto.HAS_CRYPT, 'No crypto library available')
    def test_gen_hash(self):
        """
        Test gen_hash
        """
        passwd = "test_password"
        id = "$"
        if salt.utils.platform.is_darwin():
            id = ""
        ret = salt.utils.pycrypto.gen_hash(password=passwd)
        self.assertTrue(ret.startswith("$6{0}".format(id)))

        ret = salt.utils.pycrypto.gen_hash(password=passwd, algorithm="md5")
        self.assertTrue(ret.startswith("$1{0}".format(id)))

        ret = salt.utils.pycrypto.gen_hash(password=passwd, algorithm="sha256")
        self.assertTrue(ret.startswith("$5{0}".format(id)))

    def test_secure_password(self):
        """
        test secure_password
        """
        ret = salt.utils.pycrypto.secure_password()
        check = re.compile(r"[!@#$%^&*()_=+]")
        assert check.search(ret) is None
        assert ret
