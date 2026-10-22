"""
This is a working sample CloudBolt plug-in for you to start with. The run method is required,
but you can change all the code within it. See the "CloudBolt Plug-ins" section of the docs for
more info and the CloudBolt forge for more examples:
https://github.com/CloudBoltSoftware/cloudbolt-forge/tree/master/actions/cloudbolt_plugins
"""
import json

import requests
from common.methods import set_progress
from accounts.models import Group
from infrastructure.models import CustomField, Environment
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)

# azure-mgmt-resource 25+ removed ResourceManagementClient.deployments; use the split SDK package.
# Make sure to install the package by running:
#   pip install azure-mgmt-resource-deployments==1.0.0b1
_AZURE_DEPLOYMENTS_INSTALL_HINT = (
    "ARM deployments require azure-mgmt-resource-deployments. "
    "On the CloudBolt host, install manually in the app/job Python environment, e.g.: "
    "pip install azure-mgmt-resource-deployments==1.0.0b1"
)


def _deployments_mgmt_client_class():
    try:
        from azure.mgmt.resource.deployments import DeploymentsMgmtClient

        return DeploymentsMgmtClient
    except ImportError:
        set_progress(_AZURE_DEPLOYMENTS_INSTALL_HINT)
        raise RuntimeError(_AZURE_DEPLOYMENTS_INSTALL_HINT) from None


def _deploy_arm_template(wrapper, name, resource_group, template, parameters, timeout=3600):
    """Same behavior as TechnologyWrapper.deploy_template for resource-group scoped deployments."""
    from resourcehandlers.azure_arm.azure_wrapper import _configure_arm_client

    client_cls = _deployments_mgmt_client_class()
    parameters_dict = {k: {"value": v} for k, v in parameters.items()}
    deployment_body = {
        "properties": {
            "mode": "Incremental",
            "template": template,
            "parameters": parameters_dict,
        }
    }
    deployments_client = _configure_arm_client(wrapper, client_cls)
    poller = deployments_client.deployments.begin_create_or_update(
        resource_group_name=resource_group,
        deployment_name=name,
        parameters=deployment_body,
    )
    return poller.result(timeout=timeout)


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
            'show_on_servers':True
        }
    )
    
    CustomField.objects.get_or_create(
        name="resource_group",
        type="STR",
        defaults={
            'label': "Resource Group",
            'description': 'Used by the Azure blueprints',
            'required': True,
        }
    )
    
    CustomField.objects.get_or_create(
        name="workspace_name",
        type="STR",
        defaults={
            'label': "Workspace Name",
            'description': 'The name of the Azure Databricks workspace to create.',
            'required': True,
        }
    )

    CustomField.objects.get_or_create(
        name="pricing_tier",
        type="STR",
        defaults={
            'label': "Pricing Tier",
            'description': 'The pricing tier of workspace.',
            'required': True,
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
        name="azure_deployment_id",
        type="STR",
        defaults={
            'label': "Azure Deployment ID",
            'description': 'Used by the ARM Template blueprint.',
            'required': False,
        }
    )
    
    CustomField.objects.get_or_create(
        name="azure_correlation_id",
        type="STR",
        defaults={
            'label': "Azure Databricks Correlation ID",
            'description': 'Used by the ARM Template blueprint.',
            'required': False,
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
            'show_on_servers':True
        }
    )
    
    CustomField.objects.get_or_create(
        name="azure_api_version",
        type="STR",
        defaults={
            'label': "Azure API Version",
            'description': 'Used by the ARM Template blueprint.',
            'required': False,
        }
    )


def get_arm_template():
    arm_temp = """{
      "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
      "contentVersion": "1.0.0.0",
      "parameters": {
        "disablePublicIp": {
          "type": "bool",
          "defaultValue": false,
          "metadata": {
            "description": "Specifies whether to deploy Azure Databricks workspace with Secure Cluster Connectivity (No Public IP) enabled or not"
          }
        },
        "workspaceName": {
          "type": "string",
          "metadata": {
            "description": "The name of the Azure Databricks workspace to create."
          }
        },
        "pricingTier": {
          "type": "string",
          "defaultValue": "premium",
          "allowedValues": [
            "standard",
            "premium",
            "trial"
          ],
          "metadata": {
            "description": "The pricing tier of workspace."
          }
        },
        "vnetAddressPrefix": {
          "type": "string",
          "defaultValue": "10.139",
          "metadata": {
            "description": "The first 2 octets of the virtual network /16 address range (e.g., '10.139' for the address range 10.139.0.0/16)."
          }
        },
        "location": {
          "type": "string",
          "defaultValue": "[resourceGroup().location]",
          "metadata": {
            "description": "Location for all resources."
          }
        }
      },
      "variables": {
        "managedResourceGroupName": "[concat('databricks-rg-', parameters('workspaceName'), '-', uniqueString(parameters('workspaceName'), resourceGroup().id))]"
      },
      "resources": [
        {
          "type": "Microsoft.Databricks/workspaces",
          "name": "[parameters('workspaceName')]",
          "location": "[parameters('location')]",
          "apiVersion": "2018-04-01",
          "sku": {
            "name": "[parameters('pricingTier')]"
          },
          "properties": {
            "ManagedResourceGroupId": "[subscriptionResourceId('Microsoft.Resources/resourceGroups', variables('managedResourceGroupName'))]",
            "parameters": {
              "vnetAddressPrefix": {
                "value": "[parameters('vnetAddressPrefix')]"
              },
              "enableNoPublicIp": {
                "value": "[parameters('disablePublicIp')]"
              }
            }
          }
        }
      ],
      "outputs": {
        "workspace": {
          "type": "object",
          "value": "[reference(resourceId('Microsoft.Databricks/workspaces', parameters('workspaceName')))]"
        }
      }
    }"""
    
    return arm_temp
    
    
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


def generate_options_for_resource_group(field, control_value=None, **kwargs):
    """
    Generate resource group options
    Dependency - azure region
    """
    options = []
    
    if not control_value:
        # options.insert(0, ('', '--- First, Select an Environment ---'))
        return options

    # get env object by id
    env = Environment.objects.get(id=control_value)
    
    wrapper = env.resource_handler.cast().get_api_wrapper()
    
    # fetch all resource groups
    options = [(rg.name,rg.name) for rg in wrapper.resource_client.client.resource_groups.list() if rg.location == env.node_location and rg.managed_by is None]
    
    if options:
        options = sorted(options, key=lambda tup: tup[1].lower())
        options.insert(0, ('', '--- Select a Resource Group ---'))
    else:
        options.insert(0, ('', '--- No Resource Groups found in this Environment ---'))
    
    return options
    

def generate_options_for_pricing_tier(field, **kwargs):
    return [("standard", "Standard (Apache Spark, Secure with Azure AD) $0.40/DBU-hour"), 
                ("premium", "Premium (+ Role base access controls) $0.55/DBU-hour"),
                ("trial", "Trial (Premium - 14 Days Free DBUs)")]


def run(job, *args, **kwargs):
    set_progress("Starting Provision of the databricks template...")
    
    resource = kwargs.get('resource')
    
    region = "{{azure_region}}"  # drop down
    resource_group = "{{resource_group}}" # drop down
    workspace_name = "{{workspace_name}}" # free text
    pricing_tier = "{{pricing_tier}}" # drop down
    disable_public_ip = "{{ disable_public_ip }}" # boolean true/false
    
    # get or create custom fields
    get_or_create_custom_fields()
    
    # Get environment object
    env = Environment.objects.get(id=region)
    
    # Get resource handler object
    rh = env.resource_handler.cast()
    
    deployment_name = f'{workspace_name}'
    disable_public_ip = False if disable_public_ip == "False" else True
    
    resource.name = deployment_name
    
    # Create Parameter inputs dict
    params_dict = {
        "disablePublicIp": disable_public_ip ,
        "workspaceName": deployment_name,
        "pricingTier": pricing_tier,
        "vnetAddressPrefix": "10.139",
        "location": env.node_location
    }
    
    # Generic ARM Params
    timeout = 900
    
    # Get the ARM template json
    template = json.loads(get_arm_template())
    
    logger.debug(f'Submitting request for Databricks template. deployment_name: '
                 f'{deployment_name}, resource_group: {resource_group}, '
                 f'template: {template}')
    set_progress(f'Submitting Databricks request to Azure. This can take a while.'
                 f' Timeout is set to: {timeout}')
    
    wrapper = rh.get_api_wrapper()

    # deploy databricks workspace (ARM via split SDK; azure-mgmt-resource 25+)
    deployment = _deploy_arm_template(
        wrapper,
        deployment_name,
        resource_group,
        template,
        params_dict,
        timeout=timeout,
    )

    set_progress(f'Databricks created successfully')
    logger.debug(f'deployment info: {deployment}')
    deploy_props = deployment.properties
    
    resource.azure_rh_id = rh.id
    resource.workspace_name = deployment_name
    resource.pricing_tier = pricing_tier
    resource.disable_public_ip = disable_public_ip
    resource.azure_dbs_workspace_url = "https://{0}".format(deploy_props.outputs['workspace']['value']['workspaceUrl'])
    resource.azure_region = env.node_location
    resource.azure_deployment_id = deployment.id
    resource.azure_resource_id = deploy_props.output_resources[0].id
    resource.azure_correlation_id = deploy_props.correlation_id
    resource.resource_group = resource_group
    resource.save()
    

    return "SUCCESS", "Databricks deployed successfully", ""