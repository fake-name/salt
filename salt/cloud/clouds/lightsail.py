# -*- coding: utf-8 -*-
'''
AWS Lightsail Cloud Module
==================

PLEASE NOTE: This module is currently in early development, and considered to
be experimental and unstable. It is not recommended for production use. Unless
you are actively developing code in this module, you should use the OpenStack
module instead.


.. code-block:: yaml

    my-lightsail:
      driver: lightsail
      access_key_id: AKIDMRTGYONNLTFFRBQJ
      secret_access_key: clYwH21U5UOmcov4aNV2V2XocaHCG3JZGcxEczFu

:depends: boto3 requests

'''

# Import python libs
import time
import json
import pprint
import logging
import hmac
import base64
import traceback
from hashlib import sha256

# Get logging started
log = logging.getLogger(__name__)

# Import salt libs
import salt.utils
import salt.config as config
import salt.utils.boto3
import salt.utils.compat
import salt.utils.odict as odict

import salt.utils.aws as aws_utils

import yaml
import salt.ext.six as six
try:
    import boto3  # pylint: disable=unused-import
    from botocore.exceptions import ClientError
    logging.getLogger('boto3').setLevel(logging.DEBUG)
    # logging.getLogger('boto3').setLevel(logging.CRITICAL)
    HAS_BOTO = True
except ImportError:
    HAS_BOTO = False



__virtualname__ = 'lightsail'


# Only load in this module is the Lightsail configurations are in place
def __virtual__():
    '''
    Check for Lightsail configurations
    '''
    if get_configured_provider() is False:
        return False

    if get_dependencies() is False:
        return False


    return __virtualname__

def get_configured_provider():
    '''
    Return the first configured instance.
    '''
    return config.is_provider_configured(
        __opts__,
        __active_provider_name__ or __virtualname__,
        ('id', 'key')
    )


def get_dependencies():
    '''
    Warn if dependencies aren't met.
    '''
    return config.check_driver_dependencies(
        __virtualname__,
        {'boto3': HAS_BOTO}
    )



# def _cache_provider_details(conn=None):
#     '''
#     Provide a place to hang onto results of --list-[locations|sizes|images]
#     so we don't have to go out to the API and get them every time.
#     '''
#     DETAILS['avail_locations'] = {}
#     DETAILS['avail_sizes'] = {}
#     DETAILS['avail_images'] = {}
#     locations = avail_locations(conn)
#     images = avail_images(conn)
#     sizes = avail_sizes(conn)

#     for key, location in six.iteritems(locations):
#         DETAILS['avail_locations'][location['name']] = location
#         DETAILS['avail_locations'][key] = location

#     for key, image in six.iteritems(images):
#         DETAILS['avail_images'][image['name']] = image
#         DETAILS['avail_images'][key] = image

#     for key, vm_size in six.iteritems(sizes):
#         DETAILS['avail_sizes'][vm_size['name']] = vm_size
#         DETAILS['avail_sizes'][key] = vm_size


def avail_locations(conn=None):
    '''
    return available datacenter locations
    '''
    return _query('regions/list')


def avail_sizes(conn=None):
    '''
    Return available sizes ("plans" in VultrSpeak)
    '''
    return _query('plans/list')


def avail_images(conn=None):
    '''
    Return available images
    '''
    return _query('os/list')


def list_nodes(**kwargs):
    '''
    Return basic data on nodes
    '''
    ret = {}

    nodes = list_nodes_full()
    for node in nodes:
        ret[node] = {}
        for prop in 'id', 'image', 'size', 'state', 'private_ips', 'public_ips':
            ret[node][prop] = nodes[node][prop]

    return ret


# def list_nodes_full(**kwargs):
#     '''
#     Return all data on nodes
#     '''
#     nodes = _query('server/list')
#     ret = {}

#     for node in nodes:
#         name = nodes[node]['label']
#         ret[name] = nodes[node].copy()
#         ret[name]['id'] = node
#         ret[name]['image'] = nodes[node]['os']
#         ret[name]['size'] = nodes[node]['VPSPLANID']
#         ret[name]['state'] = nodes[node]['status']
#         ret[name]['private_ips'] = nodes[node]['internal_ip']
#         ret[name]['public_ips'] = nodes[node]['main_ip']

#     return ret


# def list_nodes_select(conn=None, call=None):
#     '''
#     Return a list of the VMs that are on the provider, with select fields
#     '''
#     return __utils__['cloud.list_nodes_select'](
#         list_nodes_full(), __opts__['query.selection'], call,
#     )


# def destroy(name):
#     '''
#     Remove a node from Vultr
#     '''
#     node = show_instance(name, call='action')
#     params = {'SUBID': node['SUBID']}
#     result = _query('server/destroy', method='POST', decode=False, data=_urlencode(params))

#     # The return of a destroy call is empty in the case of a success.
#     # Errors are only indicated via HTTP status code. Status code 200
#     # effetively therefore means "success".
#     if result.get('body') == '' and result.get('text') == '':
#         return True
#     return result


# def stop(*args, **kwargs):
#     '''
#     Execute a "stop" action on a VM
#     '''
#     return _query('server/halt')


# def start(*args, **kwargs):
#     '''
#     Execute a "start" action on a VM
#     '''
#     return _query('server/start')


# def show_instance(name, call=None):
#     '''
#     Show the details from the provider concerning an instance
#     '''
#     if call != 'action':
#         raise SaltCloudSystemExit(
#             'The show_instance action must be called with -a or --action.'
#         )

#     nodes = list_nodes_full()
#     # Find under which cloud service the name is listed, if any
#     if name not in nodes:
#         return {}
#     __utils__['cloud.cache_node'](nodes[name], __active_provider_name__, __opts__)
#     return nodes[name]


# def _lookup_vultrid(which_key, availkey, keyname):
#     if DETAILS == {}:
#         _cache_provider_details()

#     which_key = str(which_key)
#     try:
#         return DETAILS[availkey][which_key][keyname]
#     except KeyError:
#         return False


# def create(vm_):
#     '''
#     Create a single VM from a data dict
#     '''
#     if 'driver' not in vm_:
#         vm_['driver'] = vm_['provider']

#     private_networking = config.get_cloud_config_value(
#         'enable_private_network', vm_, __opts__, search_global=False, default=False,
#     )

#     if private_networking is not None:
#         if not isinstance(private_networking, bool):
#             raise SaltCloudConfigError("'private_networking' should be a boolean value.")
#     if private_networking is True:
#         enable_private_network = 'yes'
#     else:
#         enable_private_network = 'no'

#     __utils__['cloud.fire_event'](
#         'event',
#         'starting create',
#         'salt/cloud/{0}/creating'.format(vm_['name']),
#         args=__utils__['cloud.filter_event']('creating', vm_, ['name', 'profile', 'provider', 'driver']),
#         sock_dir=__opts__['sock_dir'],
#         transport=__opts__['transport']
#     )

#     osid = _lookup_vultrid(vm_['image'], 'avail_images', 'OSID')
#     if not osid:
#         log.error('Vultr does not have an image with id or name {0}'.format(vm_['image']))
#         return False

#     vpsplanid = _lookup_vultrid(vm_['size'], 'avail_sizes', 'VPSPLANID')
#     if not vpsplanid:
#         log.error('Vultr does not have a size with id or name {0}'.format(vm_['size']))
#         return False

#     dcid = _lookup_vultrid(vm_['location'], 'avail_locations', 'DCID')
#     if not dcid:
#         log.error('Vultr does not have a location with id or name {0}'.format(vm_['location']))
#         return False

#     kwargs = {
#         'label': vm_['name'],
#         'OSID': osid,
#         'VPSPLANID': vpsplanid,
#         'DCID': dcid,
#         'hostname': vm_['name'],
#         'enable_private_network': enable_private_network,
#     }

#     log.info('Creating Cloud VM {0}'.format(vm_['name']))

#     __utils__['cloud.fire_event'](
#         'event',
#         'requesting instance',
#         'salt/cloud/{0}/requesting'.format(vm_['name']),
#         args={
#             'kwargs': __utils__['cloud.filter_event']('requesting', kwargs, list(kwargs)),
#         },
#         sock_dir=__opts__['sock_dir'],
#         transport=__opts__['transport'],
#     )

#     try:
#         data = _query('server/create', method='POST', data=_urlencode(kwargs))
#         if int(data.get('status', '200')) >= 300:
#             log.error('Error creating {0} on Vultr\n\n'
#                 'Vultr API returned {1}\n'.format(vm_['name'], data))
#             log.error('Status 412 may mean that you are requesting an\n'
#                       'invalid location, image, or size.')

#             __utils__['cloud.fire_event'](
#                 'event',
#                 'instance request failed',
#                 'salt/cloud/{0}/requesting/failed'.format(vm_['name']),
#                 args={'kwargs': kwargs},
#                 sock_dir=__opts__['sock_dir'],
#                 transport=__opts__['transport'],
#             )
#             return False
#     except Exception as exc:
#         log.error(
#             'Error creating {0} on Vultr\n\n'
#             'The following exception was thrown when trying to '
#             'run the initial deployment: \n{1}'.format(
#                 vm_['name'], str(exc)
#             ),
#             # Show the traceback if the debug logging level is enabled
#             exc_info_on_loglevel=logging.DEBUG
#         )
#         __utils__['cloud.fire_event'](
#             'event',
#             'instance request failed',
#             'salt/cloud/{0}/requesting/failed'.format(vm_['name']),
#             args={'kwargs': kwargs},
#             sock_dir=__opts__['sock_dir'],
#             transport=__opts__['transport'],
#         )
#         return False

#     def wait_for_hostname():
#         '''
#         Wait for the IP address to become available
#         '''
#         data = show_instance(vm_['name'], call='action')
#         main_ip = str(data.get('main_ip', '0'))
#         if main_ip.startswith('0'):
#             time.sleep(3)
#             return False
#         return data['main_ip']

#     def wait_for_default_password():
#         '''
#         Wait for the IP address to become available
#         '''
#         data = show_instance(vm_['name'], call='action')
#         # print("Waiting for default password")
#         # pprint.pprint(data)
#         if str(data.get('default_password', '')) == '':
#             time.sleep(1)
#             return False
#         return data['default_password']

#     def wait_for_status():
#         '''
#         Wait for the IP address to become available
#         '''
#         data = show_instance(vm_['name'], call='action')
#         # print("Waiting for status normal")
#         # pprint.pprint(data)
#         if str(data.get('status', '')) != 'active':
#             time.sleep(1)
#             return False
#         return data['default_password']

#     def wait_for_server_state():
#         '''
#         Wait for the IP address to become available
#         '''
#         data = show_instance(vm_['name'], call='action')
#         # print("Waiting for server state ok")
#         # pprint.pprint(data)
#         if str(data.get('server_state', '')) != 'ok':
#             time.sleep(1)
#             return False
#         return data['default_password']

#     vm_['ssh_host'] = __utils__['cloud.wait_for_fun'](
#         wait_for_hostname,
#         timeout=config.get_cloud_config_value(
#             'wait_for_fun_timeout', vm_, __opts__, default=15 * 60),
#     )
#     vm_['password'] = __utils__['cloud.wait_for_fun'](
#         wait_for_default_password,
#         timeout=config.get_cloud_config_value(
#             'wait_for_fun_timeout', vm_, __opts__, default=15 * 60),
#     )
#     __utils__['cloud.wait_for_fun'](
#         wait_for_status,
#         timeout=config.get_cloud_config_value(
#             'wait_for_fun_timeout', vm_, __opts__, default=15 * 60),
#     )
#     __utils__['cloud.wait_for_fun'](
#         wait_for_server_state,
#         timeout=config.get_cloud_config_value(
#             'wait_for_fun_timeout', vm_, __opts__, default=15 * 60),
#     )

#     __opts__['hard_timeout'] = config.get_cloud_config_value(
#         'hard_timeout',
#         get_configured_provider(),
#         __opts__,
#         search_global=False,
#         default=None,
#     )

#     # Bootstrap
#     ret = __utils__['cloud.bootstrap'](vm_, __opts__)

#     ret.update(show_instance(vm_['name'], call='action'))

#     log.info('Created Cloud VM \'{0[name]}\''.format(vm_))
#     log.debug(
#         '\'{0[name]}\' VM creation details:\n{1}'.format(
#         vm_, pprint.pformat(data)
#             )
#     )

#     __utils__['cloud.fire_event'](
#         'event',
#         'created instance',
#         'salt/cloud/{0}/created'.format(vm_['name']),
#         args=__utils__['cloud.filter_event']('created', vm_, ['name', 'profile', 'provider', 'driver']),
#         sock_dir=__opts__['sock_dir'],
#         transport=__opts__['transport']
#     )

#     return ret

def get_location(vm_=None):
    '''
    Return the EC2 region to use, in this order:
        - CLI parameter
        - VM parameter
        - Cloud profile setting
    '''
    return __opts__.get(
        'location',
        config.get_cloud_config_value(
            'location',
            vm_ or get_configured_provider(),
            __opts__,
            default=DEFAULT_LOCATION,
            search_global=False
        )
    )


def get_provider(vm_=None):
    '''
    Extract the provider name from vm
    '''
    if vm_ is None:
        provider = __active_provider_name__ or 'lightsail'
    else:
        provider = vm_.get('provider', 'lightsail')

    if ':' in provider:
        prov_comps = provider.split(':')
        provider = prov_comps[0]
    return provider


def _query(path, method='GET', data=None, params=None, header_dict=None, decode=True):
    '''
    Perform a query directly against the Vultr REST API
    '''

    try:
        # import pdb
        # pdb.set_trace()

        q_ret = aws_utils.query(product='lightsail',
                    location=aws_utils.DEFAULT_LOCATION,
                    provider=get_provider(),
                    opts=__opts__,
                    sigver='4')
        # conn = salt.utils.boto3.get_connection('lightsail', 'lightsail')
        # func = __utils__['boto3.get_connection_func']
        # conn = func('lightsail', profile='lightsail')
        print("Connection")
        print(q_ret)
    except Exception:
        traceback.print_exc()
        raise

