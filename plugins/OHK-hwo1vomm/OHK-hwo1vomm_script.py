from common.methods import set_progress
from azure.storage.blob import BlobServiceClient, PublicAccess
from resources.models import Resource, ResourceType
from infrastructure.models import CustomField
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


def create_azure_blob_sub_resource(job, resource, resource_type, blob_name, block_blob_service):
    """
    :param resource: azure storage container
    :param resource_type: azure storage container blob
    :param blob_name: blob name
    :param block_blob_service: connection object
    :return: sub resource
    """

    # fetch properties of blob
    blob_client = block_blob_service.get_blob_client(container=resource.azure_container_name, blob=blob_name)
    # Retrieve existing metadata, if desired
    detail = blob_client.get_blob_properties()
    # create sub resource of fetched blob
    res = Resource.objects.create(group=resource.group, parent_resource=resource, resource_type=resource_type,
                                  name=blob_name,
                                  blueprint=resource.blueprint, lifecycle="ACTIVE", owner=job.owner)

    res.azure_blob_size = "{:.2f}".format(float(detail.size) / float(1024)) + "kiB"
    res.azure_blob_access_tier = detail.blob_tier
    res.azure_blob_type = detail.blob_type
    res.azure_blob_content_type = detail.content_settings.content_type

    res.save()

    logger.info(f'Sub Resource {res} created successfully.')


def run(job, resource, *args, **kwargs):
    set_progress(f"Starting Provision of {resource} resource blob.")
    logger.info(f"Starting Provision of {resource} resource blob.")

    blob_name = "{{ blob_name }}"
    select_file = "{{ select_file }}"

    # get or create custom fields as needed
    get_or_create_custom_fields()

    existed_resource = Resource.objects.filter(parent_resource_id=resource.id, name=blob_name,
                                               blueprint=resource.blueprint, lifecycle="ACTIVE").first()

    if existed_resource:
        return "FAILURE", "Blob could not be created", \
               f"Blob with same name already exists in Container:{resource.azure_container_name}." \
               f"Please select different blob name"

    # resource type object for sub resource
    resource_type = get_or_create_resource_type()

    rh = AzureARMHandler.objects.get(id=resource.azure_rh_id)
    wrapper = rh.get_api_wrapper()
    storage_account_key = wrapper.storage_client.storage_accounts.list_keys(resource.resource_group_name, resource.azure_account_name).keys[0].value

     # block blob service object to establish connection
    block_blob_service = BlobServiceClient(
        account_url=f"https://{resource.azure_account_name}.blob.core.windows.net/",
        credential=storage_account_key,
    )

    set_progress(f"Uploading '{blob_name}' to Blob storage...")

    try:
        blob_client = block_blob_service.get_blob_client(container=resource.azure_container_name, blob=blob_name)
        # Upload file
        with open(select_file, "rb") as data:
            blob_client.upload_blob(data=data)
    except Exception as err:
        return "FAILURE", "blob could not be created", str(err)

    create_azure_blob_sub_resource(job, resource, resource_type, blob_name, block_blob_service)

    return "SUCCESS", f"Uploaded '{blob_name}' Successfully.", ""