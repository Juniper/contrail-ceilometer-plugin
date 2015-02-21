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

import re
import six
from six import moves
from six.moves.urllib import parse as url_parse

from ceilometer.network.statistics import driver
from ceilometer_plugin_contrail.network.statistics.opencontrail import client
from ceilometer.openstack.common import timeutils
from ceilometer_plugin_contrail import neutron_client

class OpenContrailDriver(driver.Driver):
    """Driver of network analytics of OpenContrail.

    This driver uses resources in "pipeline.yaml".

    Resource requires below conditions:

    * resource is url
    * scheme is "opencontrail"

    This driver can be configured via query parameters.
    Supported parameters:

    * scheme:
      The scheme of request url to OpenContrail Analytics endpoint.
      (default "http")
    * virtual_network
      Specify the virtual network.
      (default None)
    * fqdn_uuid:
      Specify the VM fqdn UUID.
      (default "*")
    * resource:
      The resource on which the counters are retrieved.
      (default "if_stats_list")

      * fip_stats_list:
        Traffic on floating ips
      * if_stats_list:
        Traffic on VM interfaces

    e.g.::

      opencontrail://localhost:8081/?resource=fip_stats_list&
      virtual_network=default-domain:openstack:public

    For meters ip.floating.receive.bytes, ip.floating.receive.packets
    ip.floating.transmit.bytes, ip.floating.trasmit.packets only the
    scheme configured is used. Rest of the query parameters are not
    used.

    """

    def get_sample_data(self, meter_name, parse_url, params, cache):
        sample_extractor = self._get_sample_extractor(meter_name)
        if sample_extractor is None:
            # The extractor for this meter is no implemented or the API
            # doesn't have method to get this meter.
            return
        return sample_extractor(meter_name, parse_url, params, cache)

    def _get_sample_extractor(self, meter_name):
        if meter_name.startswith('switch.port'):
            return self._get_switch_port_sample_data
        elif meter_name.startswith('ip.floating'):
            return self._get_ip_floating_sample_data
        else:
            return None

    @staticmethod
    def _prepare_cache(endpoint, params, cache):

        if 'network.statistics.opencontrail' in cache:
            return cache['network.statistics.opencontrail']

        data = {
            'o_client': client.Client(endpoint),
            'n_client': neutron_client.Client()
        }

        cache['network.statistics.opencontrail'] = data

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
        parts = url_parse.ParseResult(params.get('scheme', ['http'])[0],
                                     parse_url.netloc,
                                     parse_url.path,
                                     None,
                                     None,
                                     None)
        endpoint = url_parse.urlunparse(parts)
        extractor = self._get_extractor(meter_name)
        if extractor is None:
            return
        data = self._prepare_cache(endpoint, params, cache)

        floatingips = data['n_client'].floatingip_get_all()
        port_floatingip_map = \
            dict((floatingip['port_id'], floatingip) for floatingip in \
                    floatingips if floatingip['port_id'] is not None and \
                    floatingip['floating_ip_address'] is not None)
        for port_id in port_floatingip_map:
            port_info = data['n_client'].port_get(port_id)
            if port_info is None:
                continue
            if 'device_id' not in port_info:
                continue
            vm_fqdn_uuid = port_info['device_id']
            vm_statistics = \
                data['o_client'].networks.get_vm_statistics(vm_fqdn_uuid)
            if vm_statistics is None:
                continue
            timestamp = timeutils.utcnow().isoformat()
            floatingip_info = port_floatingip_map[port_id]
            for sample in \
                self._get_floatingip_sample(extractor, port_info,
                    floatingip_info, vm_statistics):
                if sample is not None:
                    yield sample + (timestamp,)

    @staticmethod
    def _get_floatingip_resource_meta(floatingip_info, port_info):
        resource_meta = {}
        resource_meta.update(floatingip_info)
        resource_meta['device_id'] = port_info['device_id']
        return resource_meta

    def _get_floatingip_sample(self, extractor, port_info,
                               floatingip_info, vm_statistics):
        stats = vm_statistics['UveVirtualMachineAgent'].get('fip_stats_list',
                    [])
        if type(stats) is list:
            for stat in stats:
                if 'ip_address' in stat and \
                        stat['ip_address'] == \
                        floatingip_info['floating_ip_address']:
                    rid = floatingip_info['id']
                    resource_meta = \
                        OpenContrailDriver._get_floatingip_resource_meta(
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


    """ Functions to get sample data for meters -
        switch.port.receive.bytes
        switch.port.receive.packets
        switch.port.transmit.bytes
        switch.port.transmit.packets

    """

    def _get_switch_port_sample_data(self, meter_name, parse_url, params,
                                     cache):
        parts = url_parse.ParseResult(params.get('scheme', ['http'])[0],
                                     parse_url.netloc,
                                     parse_url.path,
                                     None,
                                     None,
                                     None)
        endpoint = url_parse.urlunparse(parts)

        iter = self._get_iter(meter_name)
        if iter is None:
            # The extractor for this meter is not implemented or the API
            # doesn't have method to get this meter.
            return

        extractor = self._get_extractor(meter_name)
        if extractor is None:
            # The extractor for this meter is not implemented or the API
            # doesn't have method to get this meter.
            return

        data = self._prepare_cache(endpoint, params, cache)

        ports = data['n_client'].port_get_all()
        ports_map = dict((port['id'], port) for port in ports)

        resource = params.get('resource', ['if_stats_list'])[0]
        fqdn_uuid = params.get('fqdn_uuid', ['*'])[0]
        virtual_network = params.get('virtual_network', [None])[0]

        timestamp = timeutils.utcnow().isoformat()
        statistics = data['o_client'].networks.get_vm_statistics(fqdn_uuid)
        if not statistics:
            return

        for value in statistics['value']:
            for sample in iter(extractor, value, ports_map,
                               resource, virtual_network):
                if sample is not None:
                    yield sample + (timestamp, )

    def _get_iter(self, meter_name):
        if meter_name.startswith('switch.port'):
            return self._iter_port

    @staticmethod
    def _explode_name(fq_name):
        m = re.match(
            "(?P<domain>[^:]+):(?P<project>.+):(?P<port_id>[^:]+)",
            fq_name)
        if not m:
            return
        return m.group('domain'), m.group('project'), m.group('port_id')

    @staticmethod
    def _get_port_resource_meta(ports_map, stat, resource, network):
        if resource == 'fip_stats_list':
            if network and (network != stat['virtual_network']):
                return
            name = stat['iface_name']
        else:
            name = stat['name']

        domain, project, port_id = OpenContrailDriver._explode_name(name)
        port = ports_map.get(port_id)

        tenant_id = None
        network_id = None
        device_owner_id = None

        if port:
            tenant_id = port['tenant_id']
            network_id = port['network_id']
            device_owner_id = port['device_id']

        resource_meta = {'device_owner_id': device_owner_id,
                         'network_id': network_id,
                         'project_id': tenant_id,
                         'project': project,
                         'resource': resource,
                         'domain': domain}

        return port_id, resource_meta

    @staticmethod
    def _iter_port(extractor, value, ports_map, resource,
                   virtual_network=None):
        stats = value['value']['UveVirtualMachineAgent'].get(resource, [])
        for stat in stats:
            if type(stat) is list:
                for sub_stats, node in zip(*[iter(stat)] * 2):
                    for sub_stat in sub_stats:
                        result = OpenContrailDriver._get_port_resource_meta(
                            ports_map, sub_stat, resource, virtual_network)
                        if not result:
                            continue
                        port_id, resource_meta = result
                        yield extractor(sub_stat, port_id, resource_meta)
            else:
                result = OpenContrailDriver._get_port_resource_meta(
                    ports_map, stat, resource, virtual_network)
                if not result:
                    continue
                port_id, resource_meta = result
                yield extractor(stat, port_id, resource_meta)

    @staticmethod
    def _switch_port_receive_packets(statistic, resource_id, resource_meta):
        return int(statistic['in_pkts']), resource_id, resource_meta

    @staticmethod
    def _switch_port_transmit_packets(statistic, resource_id, resource_meta):
        return int(statistic['out_pkts']), resource_id, resource_meta

    @staticmethod
    def _switch_port_receive_bytes(statistic, resource_id, resource_meta):
        return int(statistic['in_bytes']), resource_id, resource_meta

    @staticmethod
    def _switch_port_transmit_bytes(statistic, resource_id, resource_meta):
        return int(statistic['out_bytes']), resource_id, resource_meta
