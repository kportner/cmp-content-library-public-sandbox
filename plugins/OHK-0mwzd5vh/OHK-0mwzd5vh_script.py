"""
This is a working sample CloudBolt plug-in for you to start with. The run method is required,
but you can change all the code within it. See the "CloudBolt Plug-ins" section of the docs for
more info and the CloudBolt forge for more examples:
https://github.com/CloudBoltSoftware/cloudbolt-forge/tree/master/actions/cloudbolt_plugins
"""
from infrastructure.models import CustomField
from containerorchestrators.openshifthandler.models import Openshift, OpenshiftProject
from common.methods import set_progress


def get_or_create_custom_fields():
    """
    Helper functions for main function to create custom field as needed
    """
    
    CustomField.objects.get_or_create(
        name="application_hostname",
        defaults={
            "label": "Hostname",
            "type": "STR",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )
    CustomField.objects.get_or_create(
        name="application_path",
        defaults={
            "label": "Path",
            "type": "STR",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )
    CustomField.objects.get_or_create(
        name="create_route",
        defaults={
            "label": "Create a Route to the Application",
            "type": "BOOL",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )
    
    CustomField.objects.get_or_create(
        name="application_target_port",
        defaults={
            "label": "Target Port",
            "type": "STR",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )
    

def run(job, resource, *args, **kwargs):
    set_progress("Validating advanced options form data...")
    
    # get or create custom fields as needed
    get_or_create_custom_fields()
    
    create_route = "{{create_route}}"
    hostname = "{{application_hostname}}"
    path = "{{application_path}}"
    target_port = "{{application_target_port}}"
    
    advanced_options = kwargs.get("blueprint_context", {}).get("advanced_options", {})
    
    for field in ["__untrusted_expressions", "service_item_id"]:
        if field in advanced_options:
            del advanced_options[field]
    
    if not advanced_options:
        return "FAILURE", "", f"Invalid blueprint order advanced options form data, please check and try again"
        
    return "", "", ""