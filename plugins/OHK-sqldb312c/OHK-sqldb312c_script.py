"""
Creates an SQL database in Azure.
"""
import settings
from accounts.models import Group
from common.methods import is_version_newer, set_progress
from infrastructure.models import CustomField, Environment
from azure.identity import ClientSecretCredential

cb_version = settings.VERSION_INFO["VERSION"]
CB_VERSION_93_PLUS = is_version_newer(cb_version, "9.2.1")

_AZURE_MGMT_SQL_INSTALL_HINT = (
    "Missing dependency for Azure SQL: install `azure-mgmt-sql` "
    "in the CMP appliance"
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


def _environment_is_azure(env):
    rh = env.resource_handler
    if rh is None:
        return False
    tech = getattr(rh, "resource_technology", None)
    if tech is None:
        return False
    return tech.name == "Azure"


def generate_options_for_azure_region(**kwargs):
    group_name = kwargs["group"]

    try:
        group = Group.objects.get(name=group_name)
    except Group.DoesNotExist:
        return []

    envs = list(group.get_available_environments())
    options = [(env.id, env.name) for env in envs if _environment_is_azure(env)]

    if not options:
        if not envs:
            raise RuntimeError(
                "Azure Region: this group has no environments assigned. "
                "Add environments that use an Azure resource handler."
            )
        missing_rh = sum(1 for e in envs if e.resource_handler_id is None)
        msg = (
            "Azure Region: no Azure environments for this group "
            "(%(n)s environment(s) checked; require resource handler technology 'Azure')."
            % {"n": len(envs)}
        )
        if missing_rh:
            msg += (
                " %(m)s environment(s) have no resource handler assigned on the environment."
                % {"m": missing_rh}
            )
        raise RuntimeError(msg)

    return options


def generate_options_for_resource_group(control_value=None, **kwargs):
    """Dynamically generate options for resource group form field based on the user's selection for Environment.

    This method requires the user to set the resource_group parameter as dependent on environment.
    """
    if control_value is None:
        return []

    env = Environment.objects.get(id=control_value)

    if CB_VERSION_93_PLUS:
        resource_groups = env.custom_field_options.filter(
            field__name="resource_group_arm"
        )
        return [rg.str_value for rg in resource_groups]
    else:
        rh = env.resource_handler.cast()
        groups = rh.armresourcegroup_set.all()
        return [g.name for g in groups]


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


def _get_client(handler):
    """
    Get the client using newer methods from the CloudBolt main repo if this CB is running
    a version greater than 9.2.1. These internal methods implicitly take care of much of the other
    features in CloudBolt such as proxy and ssl verification.
    Otherwise, manually instantiate clients without support for those other CloudBolt settings.
    """
    SqlManagementClient = _get_sql_mgmt_client_class()
    if SqlManagementClient is None:
        return None
    if CB_VERSION_93_PLUS:
        from resourcehandlers.azure_arm.azure_wrapper import configure_arm_client

        wrapper = handler.get_api_wrapper()
        sql_client = configure_arm_client(wrapper, SqlManagementClient)
    else:
        credentials = ClientSecretCredential(
            client_id=handler.client_id,
            client_secret=handler.secret,
            tenant_id=get_tenant_id_for_azure(handler),
        )
        sql_client = SqlManagementClient(credentials, handler.serviceaccount)

    set_progress("Connection to Azure established")

    return sql_client


def run(job, **kwargs):
    resource = kwargs.get("resource")

    create_custom_fields_as_needed()

    SqlManagementClient = _get_sql_mgmt_client_class()
    if SqlManagementClient is None:
        return "FAILURE", _AZURE_MGMT_SQL_INSTALL_HINT, _AZURE_MGMT_SQL_INSTALL_HINT

    azure_region = "{{azure_region}}"

    env = Environment.objects.get(id=azure_region)

    rh = env.resource_handler.cast()

    location = env.node_location

    set_progress("Location: %s" % location)

    resource_group = "{{ resource_group }}"

    database_name = "{{ database_name }}"

    server_name = database_name + "-server"

    server_username = "{{ server_username }}"
    server_password = "{{ server_password }}"

    sql_client = _get_client(rh)
    if sql_client is None:
        return "FAILURE", _AZURE_MGMT_SQL_INSTALL_HINT, _AZURE_MGMT_SQL_INSTALL_HINT

    set_progress('Creating server "%s"...' % server_name)
    params = {
        "location": location,
        "version": "12.0",
        "administrator_login": server_username,
        "administrator_login_password": server_password,
    }
    async_server_create = sql_client.servers.begin_create_or_update(
        resource_group,
        server_name,
        params,
    )
    while not async_server_create.done():
        set_progress("Waiting for sql server account to be created...")
        async_server_create.wait(20)

    set_progress(
        'Creating database "%s" on server "%s"...' % (database_name, server_name)
    )
    async_db_create = sql_client.databases.begin_create_or_update(
        resource_group, server_name, database_name, {"location": location}
    )
    while not async_db_create.done():
        set_progress("Waiting for sql database account to be created...")
        async_db_create.wait(20)

    database = async_db_create.result()
    assert database.name == database_name

    db = sql_client.databases.get(resource_group, server_name, database_name)
    assert db.name == database_name

    resource.name = db.name
    resource.azure_server_name = server_name
    resource.azure_database_name = db.name
    resource.azure_database_id = db.id
    resource.resource_group_name = resource_group
    resource.azure_location = location
    resource.azure_rh_id = rh.id
    resource.save()

    set_progress('Database "%s" has been created.' % database_name)
