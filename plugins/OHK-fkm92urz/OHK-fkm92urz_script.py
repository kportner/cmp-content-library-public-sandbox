"""
This is a working sample CloudBolt plug-in for you to start with. The run method is required,
but you can change all the code within it. See the "CloudBolt Plug-ins" section of the docs for
more info and the CloudBolt forge for more examples:
https://github.com/CloudBoltSoftware/cloudbolt-forge/tree/master/actions/cloudbolt_plugins
"""
from azure.storage.blob import BlobServiceClient, PublicAccess
from resources.models import Resource, ResourceType
from infrastructure.models import CustomField
from common.methods import set_progress
from utilities.logger import ThreadLogger
from resourcehandlers.azure_arm.models import AzureARMHandler

logger = ThreadLogger(__name__)


def get_or_create_custom_fields():
    """
    get_or_create_custom_fields
    """

    CustomField.objects.get_or_create(
        name='azure_blob_size', type='STR',
        defaults={
            'label': 'Azure Blob Size',
            'description': 'Used by the Azure blueprints',
            'show_as_attribute': True,
            'show_on_servers': True
        }
    )

    CustomField.objects.get_or_create(
        name='azure_blob_access_tier', type='STR',
        defaults={
            'label': 'Azure Blob Access Tier',
            'description': 'Used by the Azure blueprints',
            'show_as_attribute': True,
            'show_on_servers': True
        }
    )

    CustomField.objects.get_or_create(
        name='azure_blob_type', type='STR',
        defaults={
            'label': 'Azure Blob Type',
            'description': 'Used by the Azure blueprints',
            'show_as_attribute': True,
            'show_on_servers': True
        }
    )

    CustomField.objects.get_or_create(
        name='azure_blob_content_type', type='STR',
        defaults={
            'label': 'Azure Blob Content Type',
            'description': 'Used by the Azure blueprints',
            'show_as_attribute': True,
            'show_on_servers': True
        }
    )


def get_or_create_resource_type():
    """
    get or create resource type
    """
    rt, _ = ResourceType.objects.get_or_create(
        name="azure_storage_container_blob",
        defaults={"label": "Azure Storage container Blob", "icon": "far fa-file"}
    )

    return rt


def create_blob_cb_subresource(job, resource, resource_type, blob, block_blob_service):
    """
    Create blob 
    params: resource : resource object
    params: resource_type : resource_type object
    params: blob : azure blob object
    """
    # fetch properties of blob
    blob_client = block_blob_service.get_blob_client(container=resource.azure_container_name, blob=blob.name) 
    detail = blob_client.get_blob_properties() 
    
    # create sub resource of fetched blob 
    res = Resource.objects.create(group=resource.group, parent_resource=resource, resource_type=resource_type,
                                  name=blob.name,
                                  blueprint=resource.blueprint, lifecycle="ACTIVE", owner=job.owner)

    res.azure_blob_size = "{:.2f}".format(float(detail.size) / float(1024)) + "kiB"
    res.azure_blob_access_tier = detail.blob_tier
    res.azure_blob_type = detail.blob_type
    res.azure_blob_content_type = detail.content_settings.content_type

    res.save()
    logger.debug(f'Sub Resource {res} created successfully.')


def list_storage_container_blobs(job, block_blob_service, sub_resources, resource_type, resource):
    """
    Fetch the storage container blobs and create it on cb server if it does not exist
    Return list
    """
    discovered_objects = []

    # fetched all blobs from container 
    container_client = block_blob_service.get_container_client(container=resource.azure_container_name)
    blobs = container_client.list_blobs()

    for blob in blobs:
        discovered_objects.append(
            {
                'name': blob.name,
            })

        # search blob name in cb resource
        res = sub_resources.filter(name=blob.name).first()

        if not res:
            set_progress("Found new storage container blob '{0}', creating sub-resource...".format(blob.name))

            # create blob cb resource
            create_blob_cb_subresource(job, resource, resource_type, blob, block_blob_service)

    return discovered_objects


def run(job, resource, *args, **kwargs):
    set_progress(f"Starting Provision of {resource} resource blob.")
    logger.info(f"Starting Provision of {resource} resource blob.")

    # get or create resource type object
    resource_type = get_or_create_resource_type()
    
    # get or create blob custom fields
    get_or_create_custom_fields()

    # get all sub resource objects
    sub_resources = Resource.objects.filter(parent_resource=resource, resource_type=resource_type, lifecycle="ACTIVE")

    rh = AzureARMHandler.objects.get(id=resource.azure_rh_id)
    wrapper = rh.get_api_wrapper()
    storage_account_key = wrapper.storage_client.storage_accounts.list_keys(resource.resource_group_name, resource.azure_account_name).keys[0].value
    # block blob service object to establish connection
    block_blob_service = BlobServiceClient(
        account_url=f"https://{resource.azure_account_name}.blob.core.windows.net/",
        credential=storage_account_key,
    )

    # fetch all storage container blobs
    list_storage_container_blobs(job, block_blob_service, sub_resources, resource_type, resource)

    return "SUCCESS", "", ""