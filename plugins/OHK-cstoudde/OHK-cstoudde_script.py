"""
Discover Azure Cosmos DB records
"""
import azure.mgmt.cosmosdb as cosmosdb
from azure.common.credentials import ServicePrincipalCredentials

from common.methods import set_progress
from resourcehandlers.azure_arm.models import AzureARMHandler


RESOURCE_IDENTIFIER = "azure_account_name"

def get_tenant_id_for_azure(handler):
    '''
        Handling Azure RH table changes for older and newer versions (> 9.4.5)
    '''
    if hasattr(handler,"azure_tenant_id"):
        return handler.azure_tenant_id

    return handler.tenant_id
    

def _get_client(handler):
    """
    Get the client using newer methods from the CloudBolt main repo if this CB is running
    a version greater than 9.2. These internal methods implicitly take care of much of the other
    features in CloudBolt such as proxy and ssl verification.
    Otherwise, manually instantiate clients without support for those other CloudBolt settings.
    """
    import settings
    from common.methods import is_version_newer

    cb_version = settings.VERSION_INFO["VERSION"]
    if is_version_newer(cb_version, "9.2"):
        from resourcehandlers.azure_arm.azure_wrapper import configure_arm_client

        wrapper = handler.get_api_wrapper()
        cosmosdb_client = configure_arm_client(wrapper, cosmosdb.CosmosDBManagementClient)
    else:
        # TODO: Remove once versions <= 9.2 are no longer supported.
        credentials = ServicePrincipalCredentials(
            client_id=handler.client_id, secret=handler.secret, tenant=get_tenant_id_for_azure(rh)
        )
        cosmosdb_client = cosmosdb.CosmosDBManagementClient(credentials, handler.serviceaccount)

    set_progress("Connection to Azure established")

    return cosmosdb_client


def discover_resources(**kwargs):

    discovered_azure_cosmos = []
    for handler in AzureARMHandler.objects.all():
        set_progress("Connecting to Azure Cosmos DB for handler: {}".format(handler))
        azure_client = _get_client(handler)

        for db in azure_client.database_accounts.list():
            discovered_azure_cosmos.append(
                {
                    "name": db.name,
                    "azure_rh_id": handler.id,
                    "azure_account_name": db.name,
                    "resource_group_name": db.id.split("/")[4],
                }
            )
    return discovered_azure_cosmos