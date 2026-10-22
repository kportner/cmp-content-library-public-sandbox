from azure.storage.blob import BlobServiceClient
from common.methods import set_progress
from resources.models import ResourceType
from utilities.logger import ThreadLogger
from resourcehandlers.azure_arm.models import AzureARMHandler
from azure.core.exceptions import ResourceNotFoundError

logger = ThreadLogger(__name__)

def run(job, resource, *args, **kwargs):
    
    set_progress(f"Azure Storage Container Delete plugin running for resource: {resource}")
    logger.info(f"Azure Storage Container Delete plugin running for resource: {resource.name}")
    
    # azure container 
    container_name = resource.azure_container_name
    
    # sub resource type of blob for container resource 
    blob_type, _ = ResourceType.objects.get_or_create(name="azure_storage_container_blob")
    
    # stop execution of teardown by rerunning same job if already deleted subresource 
    if resource.resource_type.id == blob_type.id:
        return "SUCCESS", "Successfully deleted '{}'".format(resource.name), ""
    
    # block blob service object to establish connection 
    rh = AzureARMHandler.objects.get(id=resource.azure_rh_id)
    wrapper = rh.get_api_wrapper()
    storage_account_key = wrapper.storage_client.storage_accounts.list_keys(resource.resource_group_name, resource.azure_account_name).keys[0].value
    
    block_blob_service = BlobServiceClient(
        account_url=f"https://{resource.azure_account_name}.blob.core.windows.net/",
        credential=storage_account_key,
        # account_name=resource.azure_account_name,account_key=resource.azure_account_key
    )

    # check for container presence inside azure storage for same resource
    try:
        block_blob_service.delete_container(container_name)
    except Exception as error:
        return "FAILURE", f"Failed to delete container '{container_name}'", f"{error}"
    except ResourceNotFoundError:
        return "FAILURE", f"Failed to delete container '{container_name}'", f"Container don't exist."

    return "SUCCESS", f"Successfully deleted container -> '{container_name}'", ""