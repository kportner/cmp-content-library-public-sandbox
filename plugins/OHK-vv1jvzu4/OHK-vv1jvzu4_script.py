"""
Deletes an Azure queue
"""
from azure.storage.queue import QueueServiceClient

from common.methods import set_progress
from resourcehandlers.azure_arm.models import AzureARMHandler

def run(job, **kwargs):
    resource = kwargs.pop("resources").first()

    queue_name = resource.name
    azure_storage_account_name = resource.azure_storage_account_name
    azure_account_key = resource.azure_account_key
    resource_group = resource.resource_group
    set_progress("Connecting To Azure...")
    rh = AzureARMHandler.objects.get(id=resource.azure_rh_id)
    wrapper = rh.get_api_wrapper()
    storage_account_key = wrapper.storage_client.storage_accounts.list_keys(resource_group, azure_storage_account_name).keys[0].value
    
    queue_service = QueueServiceClient(
        account_url=f"https://{azure_storage_account_name}.queue.core.windows.net/",
        credential=storage_account_key
    )

    set_progress("Connection to Azure established")

    set_progress("Deleting queue %s..." % queue_name)
    queue_service.delete_queue(queue_name)

    return "Success", "The queue has been deleted", ""