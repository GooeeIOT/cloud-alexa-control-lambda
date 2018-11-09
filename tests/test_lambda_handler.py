# -*- coding: utf-8 -*-
"""
Copyright 2018 Gooee, LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from unittest import mock
from uuid import uuid4
from pathlib import Path
import json

import lambda_function
import pytest


@pytest.fixture
def fake_requests():
    """Fake Alexa Event requests"""
    return {
        "discovery_request": {
            "directive": {
                "header": {
                    "namespace": "Alexa.Discovery",
                    "name": "Discover",
                    "payloadVersion": "3",
                    "messageId": str(uuid4()),
                    "correlationToken": uuid4().hex,
                },
                "payload": {
                    "scope": {
                        "type": "BearerToken",
                        "token": "blah",
                    },
                },
            },
        },
        "report_state_request_space": {
            "directive": {
                "header": {
                    "namespace": "Alexa",
                    "name": "ReportState",
                    "payloadVersion": "3",
                    "messageId": str(uuid4()),
                    "correlationToken": uuid4().hex,
                },
                "endpoint": {
                    "scope": {
                        "type": "BearerToken",
                        "token": uuid4().hex,
                    },
                    "endpointId": "appliance-001",
                    "cookie": {
                        "type": "space",
                    }
                },
                "payload": {}
            }
        },
        "report_state_request_device": {
            "directive": {
                "header": {
                    "namespace": "Alexa",
                    "name": "ReportState",
                    "payloadVersion": "3",
                    "messageId": str(uuid4()),
                    "correlationToken": uuid4().hex,
                },
                "endpoint": {
                    "scope": {
                        "type": "BearerToken",
                        "token": uuid4().hex,
                    },
                    "endpointId": "appliance-001",
                    "cookie": {
                        "type": "device",
                    }
                },
                "payload": {}
            }
        },
        "dim": {
            "directive": {
                "header": {
                    "namespace": "Alexa.BrightnessController",
                    "name": "SetBrightness",
                    "payloadVersion": "3",
                    "messageId": str(uuid4()),
                    "correlationToken": uuid4().hex,
                },
                "endpoint": {
                    "scope": {
                        "type": "BearerToken",
                        "token": uuid4().hex
                    },
                    "endpointId": "appliance-001",
                    "cookie": {
                        "type": "space",
                    }
                },
                "payload": {
                    "brightness": 42
                }
            }
        },
        "power": {
            "directive": {
                "header": {
                    "namespace": "Alexa.PowerController",
                    "name": "TurnOn",
                    "payloadVersion": "3",
                    "messageId": str(uuid4()),
                    "correlationToken": uuid4().hex,
                },
                "endpoint": {
                    "scope": {
                        "type": "BearerToken",
                        "token": uuid4().hex
                    },
                    "endpointId": "appliance-001",
                    "cookie": {
                        "type": "device",
                    }
                },
                "payload": {
                    "brightness": 42
                }
            }
        },
        "auth": {
            "directive": {
                "header": {
                    "namespace": "Alexa.Authorization",
                    "name": "AcceptGrant",
                    "correlationToken": uuid4().hex,
                },
            },
        },
        "unhandled": {
            "directive": {
                "header": {
                    "namespace": "unhandled",
                    "name": "unhandled",
                    "correlationToken": uuid4().hex,
                },
                "endpoint": {
                    "endpointId": "appliance-001",
                },
            },
        },
    }


@mock.patch("lambda_function.g_get_request")
def test_discovery(mocked_get_req, fake_requests):
    mocked_get_req.side_effect = (
        [{"id": str(uuid4()), "name": "test space", }],
        [{"id": str(uuid4()), "name": "test device", }],
    )

    res = lambda_function.lambda_handler(fake_requests['discovery_request'], {})
    assert isinstance(res, dict)
    assert len(res['event']['payload']['endpoints']) == 2
    assert res['event']['payload']['endpoints'][0]['friendlyName'] == 'test space'
    assert res['event']['payload']['endpoints'][1]['friendlyName'] == 'test device'


@mock.patch("lambda_function.g_get_request")
def test_report_state(mocked_get_req, fake_requests):
    mocked_get_req.side_effect = (
        {
            "meta": [
                {
                    "name": "dim",
                    "value": 100,
                    "unit_of_measure": "%",
                    "groups": [
                        "~operational"
                    ],
                },
                {
                    "name": "is_online",
                    "value": False,
                    "unit_of_measure": None,
                    "groups": [
                        "~operational"
                    ],
                },
                {
                    "name": "onoff",
                    "value": True,
                    "unit_of_measure": None,
                    "groups": [
                        "~operational",
                        "~internal"
                    ],
                }
            ],
        },
        {
            "space": uuid4().hex,
            "states": {
                uuid4().hex: {"dim": 100, "onoff": True},
                uuid4().hex: {"dim": 0, "onoff": False},
            },
        },
        {
            "space": uuid4().hex,
            "states": {},
        },
    )

    # Test states for Devices
    res = lambda_function.lambda_handler(fake_requests['report_state_request_device'], {})
    assert isinstance(res, dict)
    state_names = []
    with (Path.cwd() / 'device-template.json').open('r') as fp:
        for cap in json.load(fp)['capabilities']:
            if 'properties' in cap and cap['properties']['retrievable']:
                state_names.append(cap['properties']['supported'][0]['name'])
    assert all(True if prop['name'] in state_names else False
            for prop in res['context']['properties'])

    # Test states for Spaces
    res = lambda_function.lambda_handler(fake_requests['report_state_request_space'], {})
    assert isinstance(res, dict)
    state_names = []
    with (Path.cwd() / 'space-template.json').open('r') as fp:
        for cap in json.load(fp)['capabilities']:
            if 'properties' in cap and cap['properties']['retrievable']:
                state_names.append(cap['properties']['supported'][0]['name'])
    assert all(True if prop['name'] in state_names else False
            for prop in res['context']['properties'])

    # Test empty {} device_states response, block ZeroDivisionError
    res = lambda_function.lambda_handler(fake_requests['report_state_request_space'], {})
    assert isinstance(res, dict)
    assert 'ErrorResponse' in res['event']['header']['name']

@mock.patch("lambda_function.g_post_action_request")
def test_power_controller(mocked_post_req, fake_requests):
    res = lambda_function.lambda_handler(fake_requests['power'], {})
    assert isinstance(res, dict)
    mocked_post_req.assert_called_once()
    args, _ = mocked_post_req.call_args
    assert args[0]['type'] == 'on'


@mock.patch("lambda_function.g_post_action_request")
def test_brightness_controller(mocked_post_req, fake_requests):
    brightness_value = fake_requests['dim']['directive']['payload']['brightness']
    res = lambda_function.lambda_handler(fake_requests['dim'], {})
    assert isinstance(res, dict)
    mocked_post_req.assert_called_once()
    args, _ = mocked_post_req.call_args
    assert args[0]['value']['level'] == brightness_value


def test_auth(fake_requests):
    res = lambda_function.lambda_handler(fake_requests['auth'], {})
    assert isinstance(res, dict)
    assert res['event']['header']['namespace'] == 'Alexa.Authorization'


@mock.patch("lambda_function.SENTRY_CLIENT")
def test_sentry(mock_client, fake_requests):
    res = lambda_function.lambda_handler(fake_requests['unhandled'], {})
    mock_client.captureException.assert_called_once()
    assert isinstance(res, dict)
    assert res['event']['payload']['type'] == 'INTERNAL_ERROR'


@mock.patch("lambda_function.g_post_action_request")
@mock.patch("lambda_function.g_get_request")
@mock.patch("lambda_function.SENTRY_CLIENT")
def test_error_handling(mock_client, mock_get_req, mock_post_req, fake_requests):
    mock_post_req.side_effect = lambda_function.BadRequestException('testing')
    brightness_value = fake_requests['dim']['directive']['payload']['brightness']
    res = lambda_function.lambda_handler(fake_requests['dim'], {})
    assert isinstance(res, dict)
    mock_post_req.assert_called_once()
    mock_client.captureException.assert_called_once()
    mock_client.reset_mock()
    args, _ = mock_post_req.call_args
    assert args[0]['value']['level'] == brightness_value
    assert res['event']['payload']['type'] == 'NO_SUCH_ENDPOINT'
    brightness_value = fake_requests['dim']['directive']['payload']['brightness']
    mock_post_req.reset_mock()

    mock_post_req.side_effect = lambda_function.AuthException('testing')
    res = lambda_function.lambda_handler(fake_requests['dim'], {})
    assert isinstance(res, dict)
    mock_post_req.assert_called_once()
    mock_client.captureException.assert_called_once()
    mock_client.reset_mock()
    args, _ = mock_post_req.call_args
    assert args[0]['value']['level'] == brightness_value
    assert res['event']['payload']['type'] == 'INVALID_AUTHORIZATION_CREDENTIAL'

    # Must return [] if error associated with the customer's account occurs
    mock_get_req.side_effect = lambda_function.AuthException('testing')
    res = lambda_function.lambda_handler(fake_requests['discovery_request'], {})
    assert isinstance(res, dict)
    assert len(res['event']['payload']['endpoints']) == 0
    mock_client.captureException.assert_not_called()

    # Catch 404s
    mock_get_req.side_effect = lambda_function.BadRequestException('testing')
    res = lambda_function.lambda_handler(fake_requests['report_state_request_space'], {})
    assert isinstance(res, dict)
    assert res['event']['payload']['type'] == 'NO_SUCH_ENDPOINT'
    mock_client.captureException.assert_called_once()
