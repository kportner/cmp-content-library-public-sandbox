"""
Teardown Service Item Action for AKS Cluster

Teardown the elements built by an AKS ARM Template
"""
import time
from msrestazure.azure_exceptions import CloudError

from resourcehandlers.azure_arm.models import AzureARMHandler
from containerorchestrators.kuberneteshandler.models import Kubernetes
from common.methods import set_progress
from utilities.logger import ThreadLogger


logger = ThreadLogger(__name__)

def get_api_version():
    return '2020-09-01'
 
def delete_resource(resource_client, api_version, resource_id, wrapper):
    """
    Delete azure kubernetes cluster2020-09-01   """
    try:
        response = resource_client.resources.begin_delete_by_id(resource_id, api_version)
        # Need to wait for each delete to complete in case there are
        # resources dependent on others (VM disks, etc.)
        wrapper._wait_on_operation(response)
    except:
        return False
    
    return True


def verify_resource(resource_client, resource_id, api_version, not_verified=0):
    """
    Verify azure kubernetes cluster
    """
    try:
        resource_client.resources.get_by_id(resource_id, api_version)
    except CloudError as ce:
        try:
            reason = ce.error.error
        except:
            reason = ce.error.response.reason
            
        if reason == 'ResourceNotFound' or reason == 'DeploymentNotFound' or \
                reason == 'Not Found':
            logger.info(f'resource_id: {resource_id} could not be '
                        f'found, it may have already been deleted. '
                        f'Continuing')
        else:
            logger.warn(f'Could not get resource id: {resource_id}'
                        f'Error: {ce.message}')
        
        if not_verified > 2:
            return False
        
        not_verified+=1
        time.sleep(10)
        
        # retry to verify azure kubernetes cluster
        verify_resource(resource_client, resource_id, api_version, not_verified)
        
    return True

def run(job, *args, **kwargs):
    resource = kwargs.pop('resources').first()

    if resource is None:
        set_progress("Resource was not found")
        return "SUCCESS", "Resource was not found", ""

    
    set_progress(f"ARM Delete plugin running for resource: {resource}")

    azure_rh_id = resource.azure_rh_id
    resource_id = resource.azure_resource_id
    api_version = get_api_version()

    if azure_rh_id is None:
        set_progress("No RH ID set on the blueprint, continuing")
        return "SUCCESS", "No RH ID set on the blueprint, continuing", ""
        
    # Instantiate Azure Resource Client
    rh: AzureARMHandler = AzureARMHandler.objects.get(id=azure_rh_id)
    wrapper = rh.get_api_wrapper()
    resource_client = wrapper.resource_client

    attempts = 0
    is_deleted = False
    

    while attempts < 2:
        
        # verified azure resource id
        if not verify_resource(resource_client, resource_id, api_version):
            return "WARNING", "Resource not found, it may have already been deleted", ""
        

        set_progress(f'Deleting Azure Resource with ID: '
                                f'{resource_id}, using api_version: '
                                f'{api_version}')
        
        # delete resource from azure portal
        is_deleted = delete_resource(resource_client, api_version, resource_id, wrapper)

        if is_deleted:
            break
            
        attempts+=1
            
 
    if not is_deleted:
        logger.error(f'These ID failed deletion: {resource_id}')
        return "WARNING", "Some resources failed deletion", ""
    
    try:
        kubernetes = Kubernetes.objects.get(id=resource.container_orchestrator_id)
        kubernetes.delete()
    except Kubernetes.DoesNotExist:
        pass

    return "SUCCESS", "Azure Kubernetes deleted successfully ", ""