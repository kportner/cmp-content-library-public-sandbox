"""
Discover Azure Storage Records
Return Azure Storage records identified by sku, handler_id and location
"""
from common.methods import set_progress
from azure.common.credentials import ServicePrincipalCredentials
from resourcehandlers.azure_arm.models import AzureARMHandler
import azure.mgmt.storage as storage
from infrastructure.models import CustomField

RESOURCE_IDENTIFIER = "azure_account_name"


def get_tenant_id_for_azure(handler):
    '''
        Handling Azure RH table changes for older and newer versions (> 9.4.5)
    '''
    if hasattr(handler,"azure_tenant_id"):
        return handler.azure_tenant_id

    return handler.tenant_id
    
    
def create_custom_fields_as_needed():
    CustomField.objects.get_or_create(
        name="azure_rh_id",
        type="STR",
        defaults={
            "label": "Azure RH ID",
            "description": "Used by the Azure blueprints",
            "show_as_attribute": True,
        },
    )

    CustomField.objects.get_or_create(
        name="azure_account_name",
        type="STR",
        defaults={
            "label": "Azure Account Name",
            "description": "Used by the Azure blueprints",
            "show_as_attribute": True,
        },
    )
    CustomField.objects.get_or_create(
        name="azure_account_key",
        type="STR",
        defaults={
            "label": "Azure Account Key",
            "description": "Used to authenticate this blueprint when making requests to Azure storage account",
            "show_as_attribute": True,
        },
    )
    CustomField.objects.get_or_create(
        name="azure_account_key_fallback",
        type="STR",
        defaults={
            "label": "Azure Account Key",
            "description": "Used to authenticate this blueprint when making requests to Azure storage account",
            "show_as_attribute": False,
        },
    )

    CustomField.objects.get_or_create(
        name="azure_location",
        type="STR",
        defaults={
            "label": "Azure Location",
            "description": "Used by the Azure blueprints",
            "show_as_attribute": True,
        },
    )

    CustomField.objects.get_or_create(
        name="resource_group_name",
        type="STR",
        defaults={
            "label": "Azure Resource Group",
            "description": "Used by the Azure blueprints",
            "show_as_attribute": True,
        },
    )


def _get_client(handler):
    """
    Get the clients using newer methods from the CloudBolt main repo if this CB is running
    a version greater than 9.2.2. These internal methods implicitly take care of much of the other
    features in CloudBolt such as proxy and ssl verification.
    Otherwise, manually instantiate clients without support for those other CloudBolt settings.
    """
    import settings
    from common.methods import is_version_newer

    cb_version = settings.VERSION_INFO["VERSION"]
    if is_version_newer(cb_version, "9.2.2"):
        wrapper = handler.get_api_wrapper()
        storage_client = wrapper.storage_client
    else:
        # TODO: Remove once versions <= 9.2.2 are no longer supported.
        credentials = ServicePrincipalCredentials(
            client_id=handler.client_id, secret=handler.secret, tenant=get_tenant_id_for_azure(handler)
        )
        storage_client = storage.StorageManagementClient(
            credentials, handler.serviceaccount
        )

    set_progress("Connection to Azure established")

    return storage_client


def discover_resources(**kwargs):

    discovered_az_stores = []
    for handler in AzureARMHandler.objects.all():
        set_progress(
            "Connecting to Azure Storage \
        for handler: {}".format(
                handler
            )
        )

        storage_client = _get_client(handler)
        for st in storage_client.storage_accounts.list():
            discovered_az_stores.append(
                {
                    "name": st.name,
                    "azure_rh_id": handler.id,
                    "azure_account_name": st.name,
                    "resource_group_name": st.id.split('/')[4],
                }
            )
    return discovered_az_stores