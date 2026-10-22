"""
Deletes SQL database from Azure
"""
from common.methods import set_progress
from resourcehandlers.azure_arm.models import AzureARMHandler
from azure.identity import ClientSecretCredential

_AZURE_MGMT_SQL_INSTALL_HINT = (
    "Missing dependency for Azure SQL: install `azure-mgmt-sql` "
    "in the CloudBolt app/job Python environment."
)


def _get_sql_mgmt_client_class():
    try:
        from azure.mgmt.sql import SqlManagementClient

        return SqlManagementClient
    except ImportError:
        set_progress(_AZURE_MGMT_SQL_INSTALL_HINT)
        return None


def get_tenant_id_for_azure(handler):
    """
    Handling Azure RH table changes for older and newer versions (> 9.4.5)
    """
    if hasattr(handler, "azure_tenant_id"):
        return handler.azure_tenant_id

    return handler.tenant_id


def run(job, **kwargs):
    resource = kwargs.pop("resources").first()

    server_name = resource.attributes.get(field__name="azure_server_name").value
    database_name = resource.attributes.get(field__name="azure_database_name").value
    resource_group = resource.attributes.get(field__name="resource_group_name").value
    rh_id = resource.attributes.get(field__name="azure_rh_id").value
    rh = AzureARMHandler.objects.get(id=rh_id)

    SqlManagementClient = _get_sql_mgmt_client_class()
    if SqlManagementClient is None:
        return "FAILURE", _AZURE_MGMT_SQL_INSTALL_HINT, _AZURE_MGMT_SQL_INSTALL_HINT

    set_progress("Connecting To Azure...")
    credentials = ClientSecretCredential(
        client_id=rh.client_id,
        client_secret=rh.secret,
        tenant_id=get_tenant_id_for_azure(rh),
    )
    sql_client = SqlManagementClient(credentials, rh.serviceaccount)
    set_progress("Connection to Azure established")

    set_progress("Deleting database %s from %s..." % (server_name, database_name))
    sql_client.databases.begin_delete(resource_group, server_name, database_name).wait()

    set_progress("Deleting server %s..." % server_name)
    sql_client.servers.begin_delete(resource_group, server_name).wait()

    return "", "", ""
