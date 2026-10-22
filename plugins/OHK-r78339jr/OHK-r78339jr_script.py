"""
Delete an Azure resource group and virtual network.

** See README for more details for blueprint construction **

"""
from common.methods import set_progress
from azure.common.credentials import ServicePrincipalCredentials
from msrestazure.azure_exceptions import CloudError
from resourcehandlers.azure_arm.models import AzureARMHandler
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.resource import ResourceManagementClient
from azure.identity import ClientSecretCredential
from azure.core.exceptions import HttpResponseError
###
# Main run() method
###
def run(job, **kwargs):
    # 1. Get attributes stored on meta data
    resource = kwargs.pop('resources').first()
    virtual_net_name = resource.attributes.get(field__name='azure_virtual_net_name').value
    resource_group = resource.attributes.get(field__name='resource_group_name').value
    rh_id = resource.attributes.get(field__name='azure_rh_id').value
    rh = AzureARMHandler.objects.get(id=rh_id)

    # 2. Connect to Azure
    set_progress("Connecting To Azure...")
    credentials = ClientSecretCredential(
        client_id=rh.client_id,
        client_secret=rh.secret,
        tenant_id=rh.azure_tenant_id
    )
    network_client = NetworkManagementClient(credentials, rh.serviceaccount)
    rg_client = ResourceManagementClient(credentials, rh.serviceaccount)
    set_progress("Connection to Azure established")

    # 3. Delete VNet
    set_progress("Deleting VNet[" + virtual_net_name + "] ResourceGroup[" + resource_group + "]...")
    try:
        network_client.virtual_networks.begin_delete(resource_group_name=resource_group,
                                               virtual_network_name=virtual_net_name)
        delete_async_operation = rg_client.resource_groups.begin_delete(resource_group)
        # delete_async_operation.wait()

    except CloudError as e:
        set_progress("Azure Clouderror: {}".format(e))
        return "FAILURE", "ResourceGroup and VNet could not be deleted", ""
    except HttpResponseError:
        set_progress("Azure HttpResponseError: {}".format(e))
        return "FAILURE", "ResourceGroup and VNet could not be deleted", ""
    # 4. Return results
    return "SUCCESS", "The ResourceGroup and VNet have been successfully deleted", ""