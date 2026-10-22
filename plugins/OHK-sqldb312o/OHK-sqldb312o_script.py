from msrestazure.azure_exceptions import CloudError
from azure.core.exceptions import AzureError
from infrastructure.models import CustomField
from common.methods import set_progress
from resourcehandlers.azure_arm.models import AzureARMHandler


RESOURCE_IDENTIFIER = "azure_database_id"

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
        name="azure_database_name",
        type="STR",
        defaults={
            "label": "Azure Database Name",
            "description": "Used by the Azure blueprints",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )

    CustomField.objects.get_or_create(
        name="azure_server_name",
        type="STR",
        defaults={
            "label": "Azure Server Name",
            "description": "Used by the Azure blueprints",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )

    CustomField.objects.get_or_create(
        name="azure_location",
        type="STR",
        defaults={
            "label": "Azure Location",
            "description": "Used by the Azure blueprints",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )

    CustomField.objects.get_or_create(
        name="resource_group_name",
        type="STR",
        defaults={
            "label": "Azure Resource Group",
            "description": "Used by the Azure blueprints",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )

    CustomField.objects.get_or_create(
        name="azure_database_id",
        type="STR",
        defaults={
            "label": "Azure Database ID",
            "description": "Used by the Azure blueprints",
        },
    )


def discover_resources(**kwargs):
    create_custom_fields_as_needed()

    SqlManagementClient = _get_sql_mgmt_client_class()
    if SqlManagementClient is None:
        return []

    discovered_azure_sql = []
    for handler in AzureARMHandler.objects.all():
        set_progress("Connecting to Azure sql DB for handler: {}".format(handler))

        wrapper = handler.get_api_wrapper()
        sql_client = SqlManagementClient(wrapper.credentials, handler.serviceaccount)
        azure_resources_client = wrapper.resource_client

        for resource_group in azure_resources_client.resource_groups.list():
            try:
                for server in sql_client.servers.list_by_resource_group(
                    resource_group.name
                ):
                    try:
                        for db in sql_client.databases.list_by_server(
                            resource_group.name, server.name
                        ):
                            if db.name == "master":
                                continue
                            discovered_azure_sql.append(
                                {
                                    "name": db.name,
                                    "azure_database_id": db.id,
                                    "azure_server_name": server.name,
                                    "azure_database_name": db.name,
                                    "resource_group_name": resource_group.name,
                                    "azure_rh_id": handler.id,
                                    "azure_location": db.location,
                                }
                            )
                    except (CloudError, AzureError) as e:
                        set_progress("Azure error listing databases: {}".format(e))
                        continue
            except (CloudError, AzureError) as e:
                set_progress("Azure Clouderror: {}".format(e))
                continue

    return discovered_azure_sql
