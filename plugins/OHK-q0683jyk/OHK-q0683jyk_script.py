import json

from common.methods import set_progress
from resourcehandlers.azure_arm.azure_wrapper import _configure_arm_client
from resourcehandlers.azure_arm.models import AzureARMHandler

"""
This is an example of building resources defined in a given Azure Resource Manager template.
Run this plugin as a Blueprint Action to build the resources defined in the template provided.

The parameters dict is a simple wrapper that lists all parameters defined in the template. Some of those
parameters can be exposed as action inputs, while others could be hard-coded here in this plugin,
depending on how this template might be deployed.

The template dir could be converted to accept an action input, which would convert this plugin to
be able to run any ARM template. But since various parameters are required by different templates,
writing a plugin to wrap each template is probably required.

The example template dir used here comes from https://github.com/Azure/azure-quickstart-templates
That repo lists dozens of ARM templates, any of which should be compatible with this plugin.

To convert this plugin for another template:

1) Copy the template, including the parent directory, to the CloudBolt server
2) Change the template_dir to reflect the path to the new template dir.
3) Change the 'parameters' dict to include keys for all the parameters listed in the template.
4) For each parameter value, provide either a value or a variable reference (to be converted to
    an action input)
5) Adjust timeout (default is 1 hour)

CloudBolt ships azure-mgmt-resource 25+, which no longer exposes ResourceManagementClient.deployments.
ARM deployments require the separate package azure-mgmt-resource-deployments (see _deploy_arm_template_sdk_compat).
"""

_AZURE_DEPLOYMENTS_INSTALL = (
    "ARM template deployment requires azure-mgmt-resource-deployments. "
    "Install in the CloudBolt application Python environment, e.g.: "
    "pip install azure-mgmt-resource-deployments==1.0.0b1"
)


def _deploy_arm_template_sdk_compat(
    wrapper,
    deployment_name,
    resource_group,
    template,
    parameters,
    timeout=3600,
):
    """
    Resource-group ARM deployment for azure-mgmt-resource 25+ via DeploymentsMgmtClient.
    Same approach as Azure ARM Templates UI extension shared.py (deploy_arm_template_sdk_compat).
    """
    try:
        from azure.mgmt.resource.deployments import DeploymentsMgmtClient
    except ImportError:
        set_progress(_AZURE_DEPLOYMENTS_INSTALL)
        raise RuntimeError(_AZURE_DEPLOYMENTS_INSTALL) from None

    parameters_dict = {k: {"value": v} for k, v in parameters.items()}
    deployment_body = {
        "properties": {
            "mode": "Incremental",
            "template": template,
            "parameters": parameters_dict,
        }
    }
    deployments_client = _configure_arm_client(wrapper, DeploymentsMgmtClient)
    poller = deployments_client.deployments.begin_create_or_update(
        resource_group_name=resource_group,
        deployment_name=deployment_name,
        parameters=deployment_body,
    )
    return wrapper._wait_on_operation(poller, timeout=timeout)


def run(job, logger=None, **kwargs):
    deployment_name = "{{name}}"
    resource_group = "{{resource_group}}"

    parameters = {
        "adminUsername": "{{adminUsername}}",
        "adminPassword": "{{adminPassword}}",
        "dnsLabelPrefix": "{{dnsLabelPrefix}}",
        "ubuntuOSVersion": "16.04.0-LTS",
    }
    handler = AzureARMHandler.objects.first()
    template_dir = "/var/opt/cloudbolt/proserv/arm_templates/101-vm-simple-linux/"

    timeout = "{{timeout}}"
    if timeout:
        timeout = int(timeout)
    else:
        timeout = 3600

    template_path = template_dir + "azuredeploy.json"
    with open(template_path, "r") as f:
        template = json.loads(f.read())

    wrapper = handler.get_api_wrapper()
    _deploy_arm_template_sdk_compat(
        wrapper,
        deployment_name,
        resource_group,
        template,
        parameters,
        timeout,
    )

    return "", "", ""


if __name__ == "__main__":
    from utilities.logger import ThreadLogger

    logger = ThreadLogger(__name__)
    print(run(None, logger))
