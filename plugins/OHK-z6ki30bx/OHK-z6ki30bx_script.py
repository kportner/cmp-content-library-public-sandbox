"""
This is a working sample CloudBolt plug-in for you to start with. The run method is required,
but you can change all the code within it. See the "CloudBolt Plug-ins" section of the docs for
more info and the CloudBolt forge for more examples:
https://github.com/CloudBoltSoftware/cloudbolt-forge/tree/master/actions/cloudbolt_plugins
"""
from common.methods import set_progress
from resourcehandlers.azure_arm.models import AzureARMHandler
from infrastructure.models import CustomField

RESOURCE_IDENTIFIER = 'azure_resource_id'
API_VERSION = '2022-04-01-preview'    # The supported api-versions are '2018-04-01,2021-04-01-preview,2022-04-01-preview


def get_or_create_custom_fields():
    """
    Get or create custom fields
    """
    CustomField.objects.get_or_create(
        name="azure_region",
        type="STR",
        defaults={
            'label': "Region",
            'description': 'Location for all resources.',
            'required': True,
            'show_on_servers': True
        }
    )

    CustomField.objects.get_or_create(
        name="resource_group",
        type="STR",
        defaults={
            'label': "Resource Group",
            'description': 'Used by the Azure blueprints',
            'required': True,
            'show_on_servers':True
        }
    )

    CustomField.objects.get_or_create(
        name="disable_public_ip",
        type="BOOL",
        defaults={
            'label': "Disable Public IP",
            'description': 'Specifies whether to deploy Azure Databricks workspace with Secure Cluster Connectivity (No Public IP) enabled or not',
            'required': True,
        }
    )
    
    CustomField.objects.get_or_create(
        name="azure_resource_id",
        type="STR",
        defaults={
            'label': "Azure Resource ID",
            'description': 'Used by the ARM Template blueprint.',
            'required': False,
            'show_on_servers':True
        }
    )
    
    CustomField.objects.get_or_create(
        name="azure_rh_id",
        type="STR",
        defaults={
            'label': "Azure Resource Handler ID",
            'description': 'Used by the ARM Template blueprint.',
            'required': False,
        }
    )

    CustomField.objects.get_or_create(
        name="azure_dbs_workspace_url",
        type="URL",
        defaults={
            'label': "Databricks Workspace URL",
            'description': 'Used by the ARM Template blueprint.',
            'required': False,
            'show_on_servers': True
        }
    )



def discover_resources(**kwargs):
    discovered_instances = []

    try:
        get_or_create_custom_fields()
    except Exception as e:
        set_progress(f"Error creating custom fields : {e}")

    for rh in AzureARMHandler.objects.all():

        try:
            wrapper = rh.get_api_wrapper()
        except Exception as e:
            set_progress(f"could not get wrapper: {e}")
            continue

        set_progress(
            'Connecting to Azure Databricks for handler: {}'.format(rh))

        try:
            resources = wrapper.resource_client.resources.get_by_id(
                f'/subscriptions/{rh.serviceaccount}/providers/Microsoft.Databricks/workspaces', API_VERSION)
            
            for resource in resources.additional_properties['value']:
                rg_name = resource['id'].split('/')[4]
                rg_location = resource['location']

                instance = {
                    'name': resource['name'],
                    'azure_region': rg_location,
                    'azure_rh_id': rh.id,
                    'resource_group': rg_name,
                    'workspace_name': resource['name'],
                    'pricing_tier': resource['sku']['name'],
                    'disable_public_ip': resource['properties']['parameters']['enableNoPublicIp']['value'],
                    'azure_resource_id': resource['id'],
                    'azure_dbs_workspace_url': "https://{0}".format(resource['properties']['workspaceUrl']),
                    'azure_api_version': API_VERSION,
                }

                set_progress(instance)

                discovered_instances.append(instance)

        except Exception as e:
            set_progress(f"Exception: {e}")
            continue

    return discovered_instances