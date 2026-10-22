"""
Discover Azure storage queues
"""
import azure.mgmt.storage as storage
import azure.mgmt.resource.resources as resources
from azure.identity import ClientSecretCredential
from azure.storage.queue import QueueServiceClient
from msrestazure.azure_exceptions import CloudError

from common.methods import set_progress
from resourcehandlers.azure_arm.models import AzureARMHandler


RESOURCE_IDENTIFIER = ["azure_storage_account_name", "name"]

def get_tenant_id_for_azure(handler):
    '''
        Handling Azure RH table changes for older and newer versions (> 9.4.5)
    '''
    if hasattr(handler,"azure_tenant_id"):
        return handler.azure_tenant_id

    return handler.tenant_id


def discover_resources(**kwargs):
    discovered_azure_queues = []
    for handler in AzureARMHandler.objects.all():
        set_progress(
            "Connecting to Azure storage \
        queues for handler: {}".format(
                handler
            )
        )
        wrapper = handler.get_api_wrapper()
        
        azure_client = storage.StorageManagementClient(
            wrapper.credentials, handler.serviceaccount
        )
        azure_resources_client = wrapper.resource_client
        
        for resource_group in azure_resources_client.resource_groups.list():
            try:
                for st in (azure_client.storage_accounts.list_by_resource_group(resource_group.name)):
                    try:
                        res = azure_client.storage_accounts.list_keys(
                            resource_group.name, st.name
                        )
                        keys = res.keys
                        for queue in QueueServiceClient(
                            account_name=st.name, account_key=keys[1].value
                        ).list_queues():
                            discovered_azure_queues.append(
                                {
                                    "name": queue.name,
                                    "azure_queue_name": queue.name,
                                    "resource_group": resource_group.name,
                                    "azure_rh_id": handler.id,
                                    "azure_storage_account_name": st.name,
                                    "azure_account_key": keys[0].value,
                                    "azure_account_key_fallback": keys[1].value,
                                }
                            )
                    except:  # noqa: E722
                        continue
            except CloudError as e:
                set_progress("Azure CloudError: {}".format(e))
                continue

    return discovered_azure_queues