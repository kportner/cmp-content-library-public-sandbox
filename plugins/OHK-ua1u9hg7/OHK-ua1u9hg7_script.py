import settings
from common.methods import set_progress, is_version_newer
from infrastructure.models import Environment
from azure.common.credentials import ServicePrincipalCredentials
import azure.mgmt.storage as storage
from resourcehandlers.azure_arm.models import AzureARMHandler
from azure.storage.blob import BlobServiceClient, PublicAccess
from infrastructure.models import CustomField
from accounts.models import Group
from utilities.logger import ThreadLogger
from azure.identity import ClientSecretCredential
from azure.core.exceptions import ResourceExistsError

logger = ThreadLogger(__name__)

cb_version = settings.VERSION_INFO["VERSION"]
CB_VERSION_93_PLUS = is_version_newer(cb_version, "9.2.1")


def get_tenant_id_for_azure(handler):
    '''
        Handling Azure RH table changes for older and newer versions (> 9.4.5)
    '''
    if hasattr(handler, "azure_tenant_id"):
        return handler.azure_tenant_id
    return handler.tenant_id


def generate_options_for_azure_region(**kwargs):
    group_name = kwargs["group"]

    try:
        group = Group.objects.get(name=group_name)
    except Exception as err:
        return []
    
    # fetch all group environment
    envs = group.get_available_environments()
    
    options=[(env.id, env.name) for env in envs if env.resource_handler.resource_technology.name == "Azure" ]

    if not options:
        raise RuntimeError(
            "No valid Environments on Azure resource handlers in CloudBolt"
        )

    return options


def generate_options_for_resource_group(control_value=None, **kwargs):
    """
    Generate options for azure resource group
    Dependency: Azure Region
    """

    if control_value is None:
        return []

    # environment objects
    env = Environment.objects.get(id=control_value)
    if CB_VERSION_93_PLUS:
        # Get the Resource Groups as defined on the Environment. The Resource Group is a
        # CustomField that is only updated on the Env when the user syncs this field on the
        # Environment specific parameters.
        resource_groups = env.custom_field_options.filter(
            field__name="resource_group_arm"
        )

        return [(rg.str_value, rg.str_value) for rg in resource_groups]
        
    else:
        rh = env.resource_handler.cast()
        return list(rh.armresourcegroup_set.values_list('name', flat=True))


def generate_options_for_storage_accounts(control_value=None, **kwargs):
    """
    Generate options for storage account
    Dependency:  Resource Group
    """
    storage_accounts = []
    if control_value is None or control_value == "":
        return []

    for handler in AzureARMHandler.objects.all():
        set_progress('Connecting to Azure Storage for handler: {}'.format(handler))
        credentials = ClientSecretCredential(
            client_id=handler.client_id,
            client_secret=handler.secret,
            tenant_id=get_tenant_id_for_azure(handler)
        )
        azure_client = storage.StorageManagementClient(credentials, handler.serviceaccount)
        set_progress("Connection to Azure established")
        for st in azure_client.storage_accounts.list_by_resource_group(control_value):
            storage_accounts.append(st.name)
            
    if not storage_accounts:
        return [("","No Storage Account Associated with Resource Group, Try with other Resource Group")]

    return storage_accounts


def generate_options_for_permissions(**kwargs):
    """
    Generate options for permissions
    """
    return [
        (PublicAccess.OFF, "Private (Only the owner has access)"),
        (PublicAccess.Blob, "Blob (Anonymous read access for the blobs only)"),
        (PublicAccess.Container, "Container (Anonymous read access for containers and blobs)")
        ]


def get_or_create_custom_fields():
    """
    Get or create custom field as needed
    """
    CustomField.objects.get_or_create(
        name='azure_rh_id', type='STR',
        defaults={
            'label': 'Azure RH ID',
            'description': 'Used by the Azure blueprints',
            'show_as_attribute': True,
            'show_on_servers': True
        }
    )
    CustomField.objects.get_or_create(
        name='azure_storage_container_location', type='STR',
        defaults={
            'label': 'Location',
            'description': 'Used by the Azure blueprints',
            'show_as_attribute': True,
            'show_on_servers': True
        }
    )
    CustomField.objects.get_or_create(
        name='azure_account_name', type='STR',
        defaults={
            'label': 'Azure Account Name',
            'description': 'Used by the Azure blueprints',
            'show_as_attribute': True,
            'show_on_servers': True
        }
    )
    CustomField.objects.get_or_create(
        name='azure_container_name', type='STR',
        defaults={
            'label': 'Container Name',
            'description': 'Used by the Azure blueprints',
            'show_as_attribute': True,
            'show_on_servers': True
        }
    )
    CustomField.objects.get_or_create(
        name='azure_account_key', type='STR',
        defaults={
            'label': 'Azure Account Key',
            'description': 'Used to authenticate this blueprint when making requests to Azure storage account',
            'show_as_attribute': True,
            'show_on_servers': True
        }
    )
    CustomField.objects.get_or_create(
        name='resource_group_name', type='STR',
        defaults={
            'label': 'Azure Resource Group',
            'description': 'Used by the Azure blueprints',
            'show_as_attribute': True,
            'show_on_servers': True
        }
    )

def get_public_access_permission(permission):
    if permission == 'PublicAccess.OFF':
        return PublicAccess.OFF
    elif permission == 'PublicAccess.BLOB':
        return PublicAccess.BLOB
    elif permission == 'PublicAccess.CONTAINER':
        return PublicAccess.CONTAINER

def run(job, *args, **kwargs):
    set_progress('Creating Azure Storage Container...')
    logger.info('Creating Azure Storage Container...')

    # get or create custom fields as needed
    get_or_create_custom_fields()

    resource = kwargs.get('resource')
    azure_region = '{{azure_region}}'
    resource_group = "{{resource_group}}"
    storage_account = "{{storage_accounts}}"
    permission = "{{permissions}}"
    container_name = "{{container_name}}"

    # environment object
    env = Environment.objects.get(id=azure_region)
    rh = env.resource_handler.cast()
    wrapper = rh.get_api_wrapper()
    location = env.node_location
    set_progress('Location: %s' % location)

    # credentials to establish connection to azure storage
    credentials = ClientSecretCredential(
        client_id=rh.client_id,
        client_secret=rh.secret,
        tenant_id=get_tenant_id_for_azure(rh)
    )
    # azure storage management client
    client = storage.StorageManagementClient(credentials, rh.serviceaccount)

    resource.name = container_name
    resource.azure_container_id = container_name + '-' + storage_account + '-' + location
    resource.azure_account_name = storage_account
    resource.azure_container_name = container_name
    resource.resource_group_name = resource_group
    resource.azure_storage_container_location = location
    resource.lifecycle = "ACTIVE"
    resource.azure_rh_id = rh.id
    
    # Get and save accountkey
    res = client.storage_accounts.list_keys(resource_group, storage_account)
    keys = res.keys

    resource.azure_account_key = keys[0].value
    resource.save()

    azure_account_key = resource.azure_account_key

    storage_account_key = wrapper.storage_client.storage_accounts.list_keys(resource_group, storage_account).keys[0].value
    if azure_account_key:
        block_blob_service = BlobServiceClient(
            account_url=f"https://{storage_account}.blob.core.windows.net/",
            credential=storage_account_key,
        )
        set_progress(f"Creating container named '{container_name}' ...")
        try:
            # Converting permission type. str => enum
            permission = get_public_access_permission(permission)
            set_progress('Permission: %s' % permission)
            if permission !=PublicAccess.OFF:
                set_progress(f"Setting access permissions for '{container_name}'")
                result = block_blob_service.create_container(container_name.lower(), public_access=permission)
            else:
                result = block_blob_service.create_container(container_name.lower())
        except ResourceExistsError:
            return "FAILURE", f"'{container_name}' already exists.", ""
            
        return "SUCCESS", f"'{container_name}' created successfully", ""

    return "FAILURE", f"You don't have the account key for '{storage_account}'.", ""