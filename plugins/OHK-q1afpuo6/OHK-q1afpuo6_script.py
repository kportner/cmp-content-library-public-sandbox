"""
Creates an Azure resource group and virtual network (VNet).

Pre-reqs:
-------------
1. Need a valid Azure RH with the appropriate permissions

** See README for more details for blueprint construction **

"""
from common.methods import set_progress
from infrastructure.models import CustomField
from infrastructure.models import Environment
from azure.common.credentials import ServicePrincipalCredentials
from msrestazure.azure_exceptions import CloudError
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.identity import ClientSecretCredential

###
# Generates an environment dropdown
###
def generate_options_for_env_id(server=None, **kwargs):
    envs = Environment.objects.filter(resource_handler__resource_technology__name="Azure")
    options = [(env.id, env.name) for env in envs]
    return options
        
###
# Creates custom fields
###
def create_custom_fields_as_needed():
    CustomField.objects.get_or_create(
        name='azure_rh_id', type='STR',
        defaults={'label': 'Azure RH ID', 'description': 'Used by the Azure blueprints', 'show_as_attribute': True}
    )

    CustomField.objects.get_or_create(
        name='azure_virtual_net_name', type='STR',
        defaults={'label': 'Azure Virtual network Name', 'description': 'Used by the Azure VPN blueprint',
                  'show_as_attribute': True}
    )

    CustomField.objects.get_or_create(
        name='azure_virtual_net_id', type='STR',
        defaults={'label': 'Azure Virtual network ID', 'description': 'Used by the Azure VPN blueprint',
                  'show_as_attribute': True}
    )

    CustomField.objects.get_or_create(
        name='azure_subnet_names', type='STR',
        defaults={'label': 'Azure Subnet Name', 'description': 'Used by the Azure VPN blueprint',
                  'show_as_attribute': True}
    )

    CustomField.objects.get_or_create(
        name='azure_location', type='STR',
        defaults={'label': 'Azure Location', 'description': 'Used by the Azure blueprints', 'show_as_attribute': True}
    )

    CustomField.objects.get_or_create(
        name='resource_group_name', type='STR',
        defaults={'label': 'Azure Resource Group', 'description': 'Used by the Azure blueprints',
                  'show_as_attribute': True}
    )

    CustomField.objects.get_or_create(
        name='vpn_adress_prefixes', type='STR',
        defaults={'label': 'Azure vpn adress space', 'description': 'Used by the Azure vpn blueprint',
                  'show_as_attribute': True}
    )

###
# Main Run() method
###
def run(job, **kwargs):

    # 1. Set vars
    resource = kwargs.get('resource')
    create_custom_fields_as_needed()
    env_id = '{{ env_id }}'
    env = Environment.objects.get(id=env_id)
    rh = env.resource_handler.cast()
    location = env.node_location

    resource_group = '{{ resource_group }}'
    virtual_net_name = '{{ virtual_net_name }}'
    vpn_adress_prefix = '{{ vpn_adress_prefix }}'
    subnet_adress_prefix = '{{ subnet_adress_prefix }}'
    subnet_name = virtual_net_name + '_subnet'

    # 2. Echo out
    set_progress("resource group["+resource_group+"]")
    set_progress("location[" + location + "]")
    set_progress("resource_group[" + resource_group + "]")
    set_progress("virtual_net_name[" + virtual_net_name + "]")
    set_progress("vpn_adress_prefix[" + vpn_adress_prefix + "]")
    set_progress("subnet_name[" + subnet_name + "]")
    set_progress("subnet_adress_prefix[" + subnet_adress_prefix + "]")

    # 3. Connect to Azure
    set_progress("Connecting To Azure...")
    credentials = ClientSecretCredential(
        client_id=rh.client_id,
        client_secret=rh.secret,
        tenant_id=rh.azure_tenant_id
    )
    network_client = NetworkManagementClient(credentials, rh.serviceaccount)
    rg_client = ResourceManagementClient(credentials, rh.serviceaccount)
    set_progress("Connection to Azure established")

    # 4. Create RG
    set_progress('Creating resource group "%s"...' % resource_group)
    try:
        rg_client.resource_groups.create_or_update(resource_group, {'location': location})
    except CloudError as e:
        set_progress('Azure Clouderror: {}'.format(e))

    # 5. Create the VNet
    set_progress('Creating virtual network "%s"...' % virtual_net_name)
    try:
        async_vnet_creation = network_client.virtual_networks.begin_create_or_update(
            resource_group,
            virtual_net_name,
            {
                'location': location,
                'address_space': {
                    'address_prefixes': [vpn_adress_prefix]
                }
            }
        )
        async_vnet_creation.wait()
    except CloudError as e:
        set_progress('Azure Clouderror: {}'.format(e))

    # 6. Create the Subnet in VNet
    set_progress('Creating subnet "%s"...' % subnet_name)
    try:
        async_subnet_creation = network_client.subnets.begin_create_or_update(
            resource_group,
            virtual_net_name,
            subnet_name,
            {'address_prefix': subnet_adress_prefix}
        )
        subnet_info = async_subnet_creation.result()
    except CloudError as e:
        set_progress("Azure Clouderror: {}".format(e))
        return "FAILURE", "Virtual network could not be created", e

    assert subnet_info.name == subnet_name
    set_progress('Subnet "%s" has been created.' % subnet_name)

    # 7. Set meta-data on object
    resource.name = resource_group + " - " + virtual_net_name
    resource.azure_virtual_net_name = virtual_net_name
    resource.vpn_adress_prefix = vpn_adress_prefix
    resource.resource_group_name = resource_group
    resource.azure_location = location
    resource.azure_rh_id = rh.id
    resource.azure_subnet_name = subnet_name
    resource.save()

    # 8. Return result
    return "SUCCESS", "The LZ (RG + VNet) have been successfully created", ""