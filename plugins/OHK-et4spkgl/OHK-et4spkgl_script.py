from common.methods import set_progress
import azure.mgmt.storage as storage
from resourcehandlers.azure_arm.models import AzureARMHandler
import azure.mgmt.resource.resources as resources
from infrastructure.models import CustomField

RESOURCE_IDENTIFIER = 'azure_container_id'

def get_tenant_id_for_azure(handler):
    '''
        Handling Azure RH table changes for older and newer versions (> 9.4.5)
    '''
    if hasattr(handler,"azure_tenant_id"):
        return handler.azure_tenant_id
    return handler.tenant_id
    
    
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
    
    
def discover_resources(**kwargs):
    
    try:
        get_or_create_custom_fields()
    except Exception as e:
        set_progress(f"Error creating custom fields : {e}")
    
    containers = []
    
    for handler in AzureARMHandler.objects.all():
        set_progress('Connecting to Azure storage \
        container for handler: {}'.format(handler))
        wrapper = handler.get_api_wrapper()
        azure_client = wrapper.storage_client
        azure_resources_client = wrapper.resource_client
        
        for resource_group in azure_resources_client.resource_groups.list():
            for account in azure_client.storage_accounts.list_by_resource_group(resource_group.name):
                try:    
                    for container in azure_client.blob_containers.list(resource_group_name=resource_group.name, account_name=account.name):
                        res = azure_client.storage_accounts.list_keys(
                        resource_group.name, account.name)
                        keys = res.keys
                        containers.append(
                            {
                                'name' : container.name,
                                "azure_container_name" : container.name,
                                'azure_container_id' : container.name + '-' + account.name + '-' + account.location,
                                'azure_rh_id':handler.id,
                                'azure_account_name':account.name,
                                'azure_account_key':keys[0].value,
                                'resource_group_name':resource_group.name,
                                'azure_storage_container_location': account.location
                            }
                        )
                except Exception as e:
                    pass

    return containers