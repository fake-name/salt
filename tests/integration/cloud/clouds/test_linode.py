# -*- coding: utf-8 -*-
"""
    :codeauthor: Nicole Thomas <nicole@saltstack.com>
"""

# Import Python Libs
from __future__ import absolute_import, print_function, unicode_literals
import os

# Import Salt Testing Libs
from tests.support.case import ShellCase
from tests.support.runtests import RUNTIME_VARS
from tests.support.helpers import expensiveTest, generate_random_name

# Import Salt Libs
from salt.config import cloud_providers_config


# Create the cloud instance name to be used throughout the tests
from tests.integration.cloud.helpers.cloud_test_base import TIMEOUT, CloudTest


@expensiveTest
class LinodeTest(ShellCase):
    '''
    Integration tests for the Linode cloud provider in Salt-Cloud
    '''

    def setUp(self):
        '''
        Sets up the test requirements
        '''
        super(LinodeTest, self).setUp()

        # check if appropriate cloud provider and profile files are present
        profile_str = 'linode-config'
        providers = self.run_cloud('--list-providers')
        if profile_str + ':' not in providers:
            self.skipTest(
                'Configuration file for {0} was not found. Check {0}.conf files '
                'in tests/integration/files/conf/cloud.*.d/ to run these tests.'
                .format(PROVIDER_NAME)
            )

        # check if personal access token, ssh_key_file, and ssh_key_names are present
        config = cloud_providers_config(
            os.path.join(
                RUNTIME_VARS.FILES,
                'conf',
                'cloud.providers.d',
                PROVIDER_NAME + '.conf'
            )
        )

        api = config[profile_str][PROVIDER_NAME]['apikey']
        password = config[profile_str][PROVIDER_NAME]['password']
        if api == '' or password == '':
            self.skipTest(
                'An api key and password must be provided to run these tests. Check '
                'tests/integration/files/conf/cloud.providers.d/{0}.conf'.format(
                    PROVIDER_NAME
                )
            )

    def test_instance(self):
        """
        Test creating an instance on Linode
        """
        # check if instance with salt installed returned
        ret_str = self.run_cloud(
            "-p linode-test {0}".format(self.instance_name), timeout=TIMEOUT
        )
        self.assertInstanceExists(ret_str)

        self.assertDestroyInstance()
