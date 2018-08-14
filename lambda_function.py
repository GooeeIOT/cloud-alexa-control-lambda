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

import http.client
import json
import logging
import os
import time
import uuid
from collections import Counter

API_URL = os.environ.get('API_URL') or 'api.gooee.io'
LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

# Sentry Setup
SENTRY_ENVIRONMENT = 'TMPL_SENTRY_ENVIRONMENT'
SENTRY_RELEASE = 'TMPL_SENTRY_RELEASE'
SENTRY_KEY = 'TMPL_SENTRY_KEY'
SENTRY_PARAMS = (SENTRY_ENVIRONMENT, SENTRY_RELEASE, SENTRY_KEY)
SENTRY_CLIENT = None
if not any(map(lambda p: p.startswith('TMPL_'), SENTRY_PARAMS)):
    import raven
    SENTRY_CLIENT = raven.Client(
        dsn=SENTRY_KEY,
        environment=SENTRY_ENVIRONMENT,
        release=SENTRY_RELEASE,
        transport=raven.transport.http.HTTPTransport,
    )

# Allow Devices and Spaces to be powered on/off, dim/brighten, and set to x%
with open('space-template.json') as fp:
    SPACE_TEMPLATE = json.load(fp)
with open('device-template.json') as fp:
    DEVICE_TEMPLATE = json.load(fp)

# Map of Amazon's device capabilities to Gooee's device meta values
CAPABILITY_TO_META = {
    'powerState': ('onoff', lambda val: 'ON' if val else 'OFF'),
    'brightness': ('dim', lambda val: val),
    'powerLevel': ('dim',
        lambda val: {"@type": "IntegralPowerLevel", "value": val}),
    'percentage': ('dim', lambda val: val),
    'connectivity': ('is_online',
        lambda val: {"value": "OK" if val else "UNREACHABLE"})
}


class AuthException(Exception):
    """Auth Exception from the Cloud API."""


class BadRequestException(Exception):
    """Got a 400 Bad request from the Cloud API."""


def lambda_handler(request: dict, context: dict) -> dict:
    """Main Lambda handler."""

    try:
        LOGGER.info('Directive:')
        LOGGER.info(json.dumps(request, indent=4, sort_keys=True))
        header = request['directive']['header']

        if header['name'] == 'Discover':
            response = handle_discovery(request)
        elif header['name'] == 'ReportState':
            response = handle_report_state(request)
        elif header['namespace'] == 'Alexa.PowerController':
            response = handle_power_controller(request)
        elif header['namespace'] == 'Alexa.BrightnessController':
            response = handle_brightness_controller(request)
        elif header['namespace'] == 'Alexa.Authorization':
            response = handle_auth(request)
        else:
            raise Exception

        LOGGER.info('Response:')
        LOGGER.info(json.dumps(response, indent=4, sort_keys=True))

        return response
    except Exception as err:
        error_response = {
            'event': {
                'header': {
                    'namespace': 'Alexa',
                    'name': 'ErrorResponse',
                    'messageId': str(uuid.uuid4()),
                    'correlationToken':
                        request['directive']['header']['correlationToken'],
                    'payloadVersion': '3',
                },
                'endpoint': {
                    'endpointId':
                        request['directive']['endpoint']['endpointId']
                },
                'payload': {
                    'type': 'INTERNAL_ERROR',
                    'message': 'Unhandled Error',
                }
            }
        }
        if isinstance(err, BadRequestException):
            error_response['event']['payload']['type'] = 'NO_SUCH_ENDPOINT'
            error_response['event']['payload']['message'] = err.args[0]
        elif isinstance(err, AuthException):
            error_response['event']['payload']['type'] = \
                'INVALID_AUTHORIZATION_CREDENTIAL'
            error_response['event']['payload']['message'] = err.args[0]

        if SENTRY_CLIENT:
            SENTRY_CLIENT.captureException()
        return error_response


def g_post_action_request(payload: dict, key: str):
    """Make a POST action request to the Gooee Cloud API"""
    conn = http.client.HTTPSConnection(API_URL)
    headers = {
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
    }

    payload = json.dumps(payload)

    LOGGER.info('POST Request:')
    LOGGER.info(headers)
    LOGGER.info(payload)
    conn.request('POST', '/actions', payload, headers)

    res = conn.getresponse()
    if res.status in (http.HTTPStatus.UNAUTHORIZED, http.HTTPStatus.FORBIDDEN):
        raise AuthException('Auth error')
    if res.status == http.HTTPStatus.BAD_REQUEST:
        raise BadRequestException('Device or Space not found')
    data = res.read()

    LOGGER.info('Cloud-api response:')
    LOGGER.info(data.decode('utf-8'))


def g_get_request(endpoint: str, key: str):
    """Make a GET request to the Gooee Cloud API"""
    conn = http.client.HTTPSConnection(API_URL)
    headers = {
        'Authorization': f'Bearer {key}',
    }

    LOGGER.info(f'GET Request: {endpoint}')
    LOGGER.info(headers)
    conn.request('GET', endpoint, headers=headers)

    res = conn.getresponse()
    if res.status in (http.HTTPStatus.UNAUTHORIZED, http.HTTPStatus.FORBIDDEN):
        raise AuthException('Auth error')
    data = res.read()

    LOGGER.info('Cloud-api response:')
    LOGGER.info(data.decode('utf-8'))
    return json.loads(data.decode('utf-8'))


def g_get_state(type_: str, uuid: str, bearer_token: str) -> dict:
    """Fetches the status of a Space/Device in a name, value dict"""
    if type_ == 'device':
        gooee_response = g_get_request(f'/{type_}s/{uuid}', bearer_token)
        return {meta['name']: meta['value'] for meta in gooee_response['meta']}
    else:  # space only supports dim and onoff states
        gooee_response = g_get_request(
            f'/{type_}s/{uuid}/device_states',
            bearer_token,
        )
        counter = Counter()
        for val in gooee_response['states'].values():
            counter.update(val)
        return {  # Average dim and if one device in space is on, onoff = True
            'dim': int(counter['dim'] / len(gooee_response['states'])),
            'onoff': bool(counter['onoff']),
            'is_online': True,  # hard code space to be online
        }


def handle_discovery(request: dict) -> dict:
    """Discovery Handler"""
    try:
        bearer_token = request['directive']['payload']['scope']['token']
    except KeyError:
        # As per Alexa docs: If an error such as an expired token occurs
        # during a discovery request, return an empty endpoint array and not
        # an error.
        return []

    endpoints = []

    # Get User's scoped Spaces
    try:
        res = g_get_request('/spaces/?_include=id,name', bearer_token)
    except AuthException:
        pass  # As per Alexa docs: if an error associated with the customer's
        # account occurs, the skill should return an empty endpoints array
    else:
        for space in res:
            appliance = SPACE_TEMPLATE.copy()
            appliance['friendlyName'] = space['name']
            appliance['endpointId'] = space['id']
            endpoints.append(appliance)

    # Get User's scoped Devices
    try:
        res = g_get_request(
            '/devices/?_include=name,id&type__in=wim,bulb',
            bearer_token,
        )
    except AuthException:
        pass  # As per Alexa docs: if an error associated with the customer's
        # account occurs, the skill should return an empty endpoints array
    else:
        for device in res:
            appliance = DEVICE_TEMPLATE.copy()
            appliance['friendlyName'] = device['name']
            appliance['endpointId'] = device['id']
            endpoints.append(appliance)

    response = {
        'event': {
            'header': {
                'namespace': 'Alexa.Discovery',
                'name': 'Discover.Response',
                'payloadVersion': '3',
                'messageId': str(uuid.uuid4())
            },
            'payload': {
                'endpoints': endpoints
            }
        }
    }
    return response


def handle_power_controller(request: dict) -> dict:
    """PowerController Handler"""
    request_name = request['directive']['header']['name']
    endpoint = request['directive']['endpoint']['endpointId']
    type_ = request['directive']['endpoint']['cookie']['type']
    bearer_token = request['directive']['endpoint']['scope']['token']

    if request_name == 'TurnOn':
        value = 'ON'
    else:
        value = 'OFF'

    payload = {
        'name': f'Alexa {value} request',
        'type': value.lower(),
        'value': {'transition_time': 2},
    }
    payload[type_] = endpoint

    g_post_action_request(payload, bearer_token)

    response = {
        'context': {
            'properties': [
                {
                    'namespace': 'Alexa.PowerController',
                    'name': 'powerState',
                    'value': value,
                    'timeOfSample': time.strftime(
                        '%Y-%m-%dT%H:%M:%S.00Z',
                        time.gmtime(),
                    ),

                    'uncertaintyInMilliseconds': 500,
                }
            ]
        },
        'event': {
            'header': {
                'namespace': 'Alexa',
                'name': 'Response',
                'payloadVersion': '3',
                'messageId': str(uuid.uuid4()),
                'correlationToken':
                    request['directive']['header']['correlationToken'],
            },
            'endpoint': {
                'scope': {
                    'type': 'BearerToken',
                    'token': bearer_token,
                },
                'endpointId': endpoint
            },
            'payload': {},
        }
    }
    return response


def handle_brightness_controller(request: dict) -> dict:
    """BrightnessController Handler"""
    request_name = request['directive']['header']['namespace']
    request_data = request['directive']['payload']
    bearer_token = request['directive']['endpoint']['scope']['token']
    endpoint = request['directive']['endpoint']['endpointId']
    type_ = request['directive']['endpoint']['cookie']['type']
    value = None

    payload = {type_: endpoint}

    if 'brightness' in request_data:
        value = request_data['brightness']
        payload.update({
            'name': 'Alexa brightness request',
            'type': 'dim',
            'value': {'level': value, 'transition_time': 1},
        })
        g_post_action_request(payload, bearer_token)
    elif 'brightnessDelta' in request_data:
        value = request_data['brightnessDelta']
        payload.update({
            'name': 'Alexa brightnessDelta request',
            'type': 'adjust',
            'value': {'delta': value, 'transition_time': 1},
        })
        g_post_action_request(payload, bearer_token)

    response = {
        'context': {
            'properties': [
                {
                    'namespace': request_name,
                    'name': 'brightness',
                    'value': abs(value),  # TODO: get actual value from API
                    'timeOfSample': time.strftime(
                        '%Y-%m-%dT%H:%M:%S.00Z',
                        time.gmtime(),
                    ),

                    'uncertaintyInMilliseconds': 500,
                }
            ]
        },
        'event': {
            'header': {
                'namespace': 'Alexa',
                'name': 'Response',
                'payloadVersion': '3',
                'messageId': str(uuid.uuid4()),
                'correlationToken':
                    request['directive']['header']['correlationToken'],
            },
            'endpoint': {
                'scope': {
                    'type': 'BearerToken',
                    'token': bearer_token,
                },
                'endpointId': endpoint
            },
            'payload': {},
        }
    }
    return response


def handle_auth(request: dict) -> dict:
    """Authorization Handler"""
    request_name = request['directive']['header']['name']

    if request_name == 'AcceptGrant':
        response = {
            'event': {
                'header': {
                    'namespace': 'Alexa.Authorization',
                    'name': 'AcceptGrant.Response',
                    'payloadVersion': '3',
                    'messageId': str(uuid.uuid4()),
                },
                'payload': {},
            }
        }
        return response


def handle_report_state(request: dict) -> dict:
    """ReportState Handler"""
    endpoint = request['directive']['endpoint']['endpointId']
    type_ = request['directive']['endpoint']['cookie']['type']
    bearer_token = request['directive']['endpoint']['scope']['token']

    gooee_state = g_get_state(type_, uuid, bearer_token)

    properties = []

    capabilities = (SPACE_TEMPLATE['capabilities']
            if type_ == 'space' else DEVICE_TEMPLATE['capabilities'])
    for capability in capabilities:
        try:
            if not capability['properties']['retrievable']:
                continue
        except KeyError:
            continue
        amz_name = capability['properties']['supported'][0]['name']
        property_ = {
            'namespace': capability['interface'],
            'name': amz_name,
            'timeOfSample': time.strftime(
                '%Y-%m-%dT%H:%M:%S.00Z',
                time.gmtime(),
            ),

            'uncertaintyInMilliseconds': 500,
        }
        # Translate Gooee meta to how Alexa expects it, for example:
        # if gooee_state was {'onoff': True} transfunc will return 'ON'
        gooee_name, transfunc = CAPABILITY_TO_META[amz_name]
        property_['value'] = transfunc(gooee_state[gooee_name])

        properties.append(property_)

    response = {
        'context': {
            'properties': properties,
        },
        'event': {
            'header': {
                'namespace': 'Alexa',
                'name': 'StateReport',
                'payloadVersion': '3',
                'messageId': str(uuid.uuid4()),
                'correlationToken':
                    request['directive']['header']['correlationToken'],
            },
            'endpoint': {
                'scope': {
                    'type': 'BearerToken',
                    'token': bearer_token,
                },
                'endpointId': endpoint
            },
            'payload': {
            },
        }
    }
    return response
