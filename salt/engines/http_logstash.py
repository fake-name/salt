# -*- coding: utf-8 -*-
"""
HTTP Logstash engine
==========================

An engine that reads messages from the salt event bus and pushes
them onto a logstash endpoint via HTTP requests.

.. versionchanged:: 2018.3.0

.. note::
    By default, this engine take everything from the Salt bus and exports into
    Logstash.
    For a better selection of the events that you want to publish, you can use
    the ``tags`` and ``funs`` options.

:configuration: Example configuration

    .. code-block:: yaml

        engines:
          - http_logstash:
              url: http://blabla.com/salt-stuff
              tags:
                  - salt/job/*/new
                  - salt/job/*/ret/*
              funs:
                  - probes.results
                  - bgp.config
"""

from __future__ import absolute_import, print_function, unicode_literals

# Import python lib
import fnmatch

import salt.utils.event

# Import salt libs
import salt.utils.http
import salt.utils.json

# ----------------------------------------------------------------------------------------------------------------------
# module properties
# ----------------------------------------------------------------------------------------------------------------------

_HEADERS = {"Content-Type": "application/json"}

# ----------------------------------------------------------------------------------------------------------------------
# module properties
# ----------------------------------------------------------------------------------------------------------------------

# ----------------------------------------------------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------------------------------------------------


def _logstash(url, data):
    """
    Issues HTTP queries to the logstash server.
    """
    result = salt.utils.http.query(
        url,
        "POST",
        header_dict=_HEADERS,
        data=salt.utils.json.dumps(data),
        decode=True,
        status=True,
        opts=__opts__,
    )
    return result


# ----------------------------------------------------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------------------------------------------------


def start(url, funs=None, tags=None):
    """
    Listen to salt events and forward them to logstash.

    url
        The Logstash endpoint.

    funs: ``None``
        A list of functions to be compared against, looking into the ``fun``
        field from the event data. This option helps to select the events
        generated by one or more functions.
        If an event does not have the ``fun`` field in the data section, it
        will be published. For a better selection, consider using the ``tags``
        option.
        By default, this option accepts any event to be submitted to Logstash.

    tags: ``None``
        A list of pattern to compare the event tag against.
        By default, this option accepts any event to be submitted to Logstash.
    """
    if __opts__.get("id").endswith("_master"):
        instance = "master"
    else:
        instance = 'minion'
    with salt.utils.event.get_event(
        instance,
        sock_dir=__opts__["sock_dir"],
        transport=__opts__["transport"],
        opts=__opts__,
    ) as event_bus:
        while True:
            event = event_bus.get_event(full=True)
            if event:
                publish = True
                if tags and isinstance(tags, list):
                    found_match = False
                    for tag in tags:
                        if fnmatch.fnmatch(event["tag"], tag):
                            found_match = True
                    publish = found_match
                if funs and "fun" in event["data"]:
                    if not event["data"]["fun"] in funs:
                        publish = False
                if publish:
                    _logstash(url, event['data'])
