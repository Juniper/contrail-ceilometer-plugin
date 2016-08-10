#
# Copyright (c) 2015 Juniper Networks, Inc. All rights reserved.
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

from oslo_utils import timeutils
from six.moves.urllib import parse as urlparse

from ceilometer.network.statistics import driver
from ceilometer_plugin_contrail.network.statistics.contrail import client
from ceilometer import neutron_client
from ceilometer import keystone_client


class ContrailDriver(driver.Driver):
    """Driver of network analytics for Contrail.

    This driver uses resources in "pipeline.yaml".

    Resource requires below conditions:

    * resource is url
    * scheme is "contrail"

    This driver can be configured via query parameters.
    Supported parameters:

    * scheme:
      The scheme of request url to Contrail Analytics endpoint.
      (default "http")

    e.g.::

      contrail://localhost:8081/

    """

    def get_sample_data(self, meter_name, parse_url, params, cache):
        sample_extractor = self._get_sample_extractor(meter_name)
        if sample_extractor is None:
            # The extractor for this meter is no implemented or the API
            # doesn't have method to get this meter.
            return
        return sample_extractor(meter_name, parse_url, params, cache)

    def _get_sample_extractor(self, meter_name):
        if meter_name.startswith('ip.floating'):
            return self._get_ip_floating_sample_data
        else:
            return None

    @staticmethod
    def _prepare_cache(endpoint, params, cache):

        if 'network.statistics.contrail' in cache:
            return cache['network.statistics.contrail']

        data = {
            'o_client': client.Client(endpoint),
            'n_client': neutron_client.Client(),
            'ks_client': keystone_client.get_client()
        }

        cache['network.statistics.contrail'] = data

        return data

    def _get_extractor(self, meter_name):
        method_name = '_' + meter_name.replace('.', '_')
        return getattr(self, method_name, None)

    """ Functions to get sample data for meters -
        ip.floating.receive.bytes
        ip.floating.receive.packets
        ip.floating.transmit.bytes
        ip.floating.transmit.packets

    """

    def _get_ip_floating_sample_data(self, meter_name, parse_url, params,
                                     cache):
        parts = urlparse.ParseResult(params.get('scheme', ['http'])[0],
                                     parse_url.netloc,
                                     parse_url.path,
                                     None,
                                     None,
                                     None)
        endpoint = urlparse.urlunparse(parts)
        extractor = self._get_extractor(meter_name)
        if extractor is None:
            return
        data = self._prepare_cache(endpoint, params, cache)

        resp = data['n_client'].client.list_floatingips()
        floatingips = resp.get('floatingips')
        port_floatingip_map = \
            dict((floatingip['port_id'], floatingip) for floatingip in \
                    floatingips if floatingip['port_id'] is not None and \
                    floatingip['floating_ip_address'] is not None)
        for port_id in port_floatingip_map:
            resp = data['n_client'].client.show_port(port_id)
            port_info = resp.get('port')
            if port_info is None or 'device_id' not in port_info:
                continue
            vm_fqdn_uuid = port_info['device_id']
            vm_interfaces = \
                data['o_client'].networks.get_vm_interfaces(vm_fqdn_uuid,
                    token=keystone_client.get_auth_token(data['ks_client']))
            if vm_interfaces is None:
                continue
            for vmi_fqdn_uuid in vm_interfaces:
                vmi_fip_stats = \
                    data['o_client'].networks.get_vmi_fip_stats(vmi_fqdn_uuid,
                        token=keystone_client.get_auth_token(data['ks_client']))
                if vmi_fip_stats is None:
                    continue
                timestamp = timeutils.utcnow().isoformat()
                floatingip_info = port_floatingip_map[port_id]
                for sample in \
                    self._get_floatingip_sample(extractor, port_info,
                        floatingip_info, vmi_fip_stats):
                    if sample is not None:
                        yield sample + (timestamp,)

    @staticmethod
    def _get_floatingip_resource_meta(floatingip_info, port_info):
        resource_meta = {}
        resource_meta.update(floatingip_info)
        resource_meta['device_id'] = port_info['device_id']
        return resource_meta

    def _get_floatingip_sample(self, extractor, port_info,
                               floatingip_info, vmi_fip_stats):
        for stat in vmi_fip_stats:
            if 'ip_address' in stat and \
                    stat['ip_address'] == \
                    floatingip_info['floating_ip_address']:
                rid = floatingip_info['id']
                resource_meta = \
                    ContrailDriver._get_floatingip_resource_meta(
                        floatingip_info, port_info)
                yield extractor(stat, rid, resource_meta)

    @staticmethod
    def _ip_floating_receive_packets(statistic, resource_id, resource_meta):
        return int(statistic['in_pkts']), resource_id, resource_meta

    @staticmethod
    def _ip_floating_transmit_packets(statistic, resource_id, resource_meta):
        return int(statistic['out_pkts']), resource_id, resource_meta

    @staticmethod
    def _ip_floating_receive_bytes(statistic, resource_id, resource_meta):
        return int(statistic['in_bytes']), resource_id, resource_meta

    @staticmethod
    def _ip_floating_transmit_bytes(statistic, resource_id, resource_meta):
        return int(statistic['out_bytes']), resource_id, resource_meta
