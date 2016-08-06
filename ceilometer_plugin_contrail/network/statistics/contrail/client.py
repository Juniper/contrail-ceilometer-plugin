# Copyright (C) 2014 eNovance SAS <licensing@enovance.com>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import copy

from oslo_config import cfg
import requests
import six
from six.moves.urllib import parse as urlparse

from ceilometer.i18n import _  # noqa
from oslo_log import log

CONF = cfg.CONF
CONF.import_opt('http_timeout', 'ceilometer.service')

LOG = log.getLogger(__name__)


class OpencontrailAPIFailed(Exception):
    pass


class AnalyticsAPIBaseClient(object):
    """Opencontrail Base Statistics REST API Client."""

    def __init__(self, endpoint, data):
        self.endpoint = endpoint
        self.data = data or {}

    def request(self, path, fqdn_uuid, query=None, token=None, data=None):
        req_data = copy.copy(self.data)
        if data:
            req_data.update(data)

        req_params = self._get_req_params(token=token, data=req_data)

        if query:
            query_string = '?' + query
        url = urlparse.urljoin(self.endpoint, path + fqdn_uuid + query_string)
        self._log_req(url, req_params)
        resp = requests.get(url, **req_params)
        self._log_res(resp)

        if resp.status_code != 200:
            raise OpencontrailAPIFailed(
                _('Opencontrail API returned %(status)s %(reason)s') %
                {'status': resp.status_code, 'reason': resp.reason})

        return resp

    def _get_req_params(self, token=None, data=None):
        req_params = {
            'headers': {
                'Accept': 'application/json'
            },
            'data': data,
            'allow_redirects': False,
            'timeout': CONF.http_timeout,
        }
        if token is not None:
            req_params['headers']['X-Auth-Token'] = token
        return req_params

    @staticmethod
    def _log_req(url, req_params):
        if not CONF.debug:
            return

        curl_command = ['REQ: curl -i -X GET ']

        params = []
        for name, value in six.iteritems(req_params['data']):
            params.append("%s=%s" % (name, value))

        curl_command.append('"%s?%s" ' % (url, '&'.join(params)))

        for name, value in six.iteritems(req_params['headers']):
            curl_command.append('-H "%s: %s" ' % (name, value))

        LOG.debug(''.join(curl_command))

    @staticmethod
    def _log_res(resp):
        if not CONF.debug:
            return

        dump = ['RES: \n', 'HTTP %.1f %s %s\n' % (resp.raw.version,
                                                  resp.status_code,
                                                  resp.reason)]
        dump.extend('%s: %s\n' % (k, v)
                    for k, v in six.iteritems(resp.headers))
        dump.append('\n')
        if resp.content:
            dump.extend([resp.content, '\n'])

        LOG.debug(''.join(dump))


class NetworksAPIClient(AnalyticsAPIBaseClient):
    """Opencontrail Statistics REST API Client."""

    def get_vm_interfaces(self, fqdn_uuid, token=None, data=None):
        """Get interfaces of a virtual machine.
        URL:
            {endpoint}/analytics/uves/virtual-machine/{fqdn_uuid}?
            cfilt=UveVirtualMachineAgent:interface_list
        """
        path = '/analytics/uves/virtual-machine/'
        qstring = 'cfilt=UveVirtualMachineAgent:interface_list'
        resp = self.request(path, fqdn_uuid, query=qstring, token=token, data=data)
        rdict = resp.json()
        if (not rdict or not isinstance(rdict, dict) or
                'UveVirtualMachineAgent' not in rdict):
            return None
        return rdict['UveVirtualMachineAgent'].get('interface_list', None)
    #end get_vm_interfaces

    def get_vmi_fip_stats(self, fqdn_uuid, token=None, data=None):
        """Get floating IP statistics of a virtual machine interface.
        URL:
            {endpoint}/analytics/uves/virtual-machine-interface/{fqdn_uuid}?
            cfilt=UveVMInterfaceAgent:fip_agg_stats
        """
        path = '/analytics/uves/virtual-machine-interface/'
        qstring = 'cfilt=UveVMInterfaceAgent:fip_agg_stats'
        resp = self.request(path, fqdn_uuid, query=qstring, token=token, data=data)
        rdict = resp.json()
        if (not rdict or not isinstance(rdict, dict) or
                'UveVMInterfaceAgent' not in rdict):
            return None
        return rdict['UveVMInterfaceAgent'].get('fip_agg_stats', None)
    #end get_vmi_fip_stats

class Client(object):

    def __init__(self, endpoint, data=None):
        self.networks = NetworksAPIClient(endpoint, data)
