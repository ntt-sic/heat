# vim: tabstop=4 shiftwidth=4 softtabstop=4

#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from heat.common import exception
from heat.engine import clients
from heat.engine.resources.neutron import neutron
from heat.engine import scheduler

if clients.neutronclient is not None:
    from neutronclient.common.exceptions import NeutronClientException
    from neutronclient.neutron import v2_0 as neutronV20

from heat.openstack.common import log as logging

logger = logging.getLogger(__name__)


class NetworkGateway(neutron.NeutronResource):

    devices_schema = {'id': {'Type': 'String',
                             'Required': True},
                      'interface_name': {'Type': 'String',
                                         'Required': True}
                      }

    properties_schema = {'name': {'Type': 'String'},
                         'tenant_id': {'Type': 'String'},
                         'devices': {'Type': 'List',
                                     'Schema': {
                                         'Type': 'Map',
                                         'Schema': devices_schema},
                                     'Required': True},
                         }

    attributes_schema = {
        "name": _("The name of network gateway."),
        "tenant_id": _("Tenant owning the network gateway."),
        "devices": _("Device info for this network gateway."),
        "default": _("A boolean value of default flag."),
        "show": _("All attributes.")
    }

    def handle_create(self):
        props = self.prepare_properties(
            self.properties,
            self.physical_resource_name())
        network_gateway = self.neutron().create_network_gateway(
            {'network_gateway': props})['network_gateway']
        self.resource_id_set(network_gateway['id'])

    def _show_resource(self):
        return self.neutron().show_network_gateway(
            self.resource_id)['network_gateway']

    def handle_delete(self):
        client = self.neutron()
        try:
            client.delete_network_gateway(self.resource_id)
        except NeutronClientException as ex:
            if ex.status_code != 404:
                raise ex
        else:
            return scheduler.TaskRunner(self._confirm_delete)()


class NetworkGatewayConnection(neutron.NeutronResource):

    properties_schema = {'network_gateway_id': {'Type': 'String',
                                                'Required': True},
                         'network_id': {'Type': 'String',
                                        'Required': True},
                         'segmentation_type': {'Type': 'String',
                                               'Required': True,
                                               'AllowedValues': [
                                                   'flat', 'vlan']},
                         'segmentation_id': {'Type': 'Integer'}
                         }

    attributes_schema = {
        "network_gateway_id": _("Gateway owing gateway connection."),
        "network_id": _("Network you wish creating the gateway port."),
        "port_id": _("Gateway port ID for the gateway"),
        "show": _("All attributes.")
    }

    def validate(self):
        '''
        Validate any of the provided params
        '''
        super(NetworkGatewayConnection, self).validate()
        segmentation_type = self.properties.get('segmentation_type')
        segmentation_id = self.properties.get('segmentation_id')
        if segmentation_type == 'vlan' and segmentation_id is None:
            msg = 'segmentation_id must be specified for using vlan'
            raise exception.StackValidationFailed(message=msg)
        if segmentation_type == 'flat' and segmentation_id:
            msg = 'segmentation_id cannot be specified except 0 for using flat'
            raise exception.StackValidationFailed(message=msg)

    def handle_create(self):
        gateway_id = self.properties.get('network_gateway_id')
        network_id = neutronV20.find_resourceid_by_name_or_id(
            self.neutron(),
            'network',
            self.properties.get('network_id'))
        segmentation_type = self.properties.get('segmentation_type')
        segmentation_id = self.properties.get('segmentation_id')
        arg = {'network_id': network_id,
               'segmentation_type': segmentation_type}
        if segmentation_id is not None:
            arg['segmentation_id'] = int(segmentation_id)
        ret = self.neutron().connect_network_gateway(
            gateway_id, arg
        )
        port_id = ret['connection_info']['port_id']
        self.resource_id_set(
            '%s:%s:%s:%s:%s' %
            (gateway_id, network_id,
                segmentation_type, segmentation_id, port_id))

    def handle_delete(self):
        if not self.resource_id:
            return
        client = self.neutron()
        (gateway_id, network_id, segmentation_type,
         segmentation_id, port_id) = self.resource_id.split(':')
        try:
            arg = {'network_id': network_id,
                   'segmentation_type': segmentation_type}
            if segmentation_id != 'None':
                arg['segmentation_id'] = int(segmentation_id)
            client.disconnect_network_gateway(gateway_id, arg)
        except NeutronClientException as ex:
            if ex.status_code != 404:
                raise ex

    def _show_resource(self):
        (gateway_id, network_id, segmentation_type,
         segmentation_id, port_id) = self.resource_id.split(':')
        return {'network_gateway_id': gateway_id,
                'network_id': network_id,
                'segmentation_type': segmentation_type,
                'segmentation_id': int(segmentation_id),
                'port_id': port_id}


def resource_mapping():
    if clients.neutronclient is None:
        return {}

    return {
        'OS::Neutron::NetworkGateway': NetworkGateway,
        'OS::Neutron::NetworkGatewayConnection': NetworkGatewayConnection,
    }
