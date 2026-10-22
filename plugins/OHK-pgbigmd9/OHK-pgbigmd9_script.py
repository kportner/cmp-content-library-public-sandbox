"""
This is a working sample CloudBolt plug-in for you to start with. The run method is required,
but you can change all the code within it. See the "CloudBolt Plug-ins" section of the docs for
more info and the CloudBolt forge for more examples:
https://github.com/CloudBoltSoftware/cloudbolt-forge/tree/master/actions/cloudbolt_plugins
"""
import requests
import json

from common.methods import set_progress
from infrastructure.models import CustomField
from resourcehandlers.azure_arm.models import AzureARMHandler
from resources.models import Resource
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)


def get_token(rs, client_id, client_secret, tenantId):
    '''
    Generate AD and Management Access Token
    '''
    
    as_header = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    data = {
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret,
        'resource': rs
    }
    
    # get token
    resp = requests.get(f'https://login.microsoftonline.com/{tenantId}/oauth2/token', headers= as_header, data=data)
    
    if resp.status_code != 200:
        raise RuntimeError("Unable to get AD or Management access token")
        
    return resp.json()['access_token']


    
def _delete_databricks_cluster(rh, dbricks_workspace, resource_group, databricks_workspace_url, sb_resource):
    
    # Get a token for the global Databricks application. This value is fixed and never changes.
    adbToken = get_token("2ff814a6-3304-4ab8-85cb-cd0e6f879c1d", rh.client_id, rh.secret, rh.azure_tenant_id)

    # Get a token for the Azure management API
    azToken = get_token("https://management.core.windows.net/", rh.client_id, rh.secret, rh.azure_tenant_id)
    
    dbricks_auth = {
        "Authorization": f"Bearer {adbToken}",
        "X-Databricks-Azure-SP-Management-Token": azToken,
        "X-Databricks-Azure-Workspace-Resource-Id": (
            f"/subscriptions/{rh.serviceaccount}"
            f"/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Databricks"
            f"/workspaces/{dbricks_workspace}")}
    
    # delete databricks workspace cluster
    ds_rsp = requests.post(f"{databricks_workspace_url}/api/2.0/clusters/permanent-delete", headers=dbricks_auth, data=json.dumps({"cluster_id": sb_resource.dbs_cluster_id}))
    
    if ds_rsp.status_code in [200]:
        # delete cb sub resource
        sb_resource.delete()
    else:
        raise RuntimeError(ds_rsp.json()) 
    
def generate_options_for_dbs_cluster_id(field, **kwargs):
    """
    Return clusters
    """
    resource = kwargs.get("resource", None)

    if resource is None:
        return []
    
    sb_resources = Resource.objects.filter(parent_resource=resource, lifecycle="ACTIVE")
    
    options = [(xx.id, xx.name) for xx in sb_resources]
    
    return options
    
def run(job, *args, **kwargs):
    set_progress("Deleting the databricks workspace cluster...")
    logger.info("Deleting the databricks workspace cluster...")
    
    resource = kwargs.get('resource')
    
    # get resource handler object
    rh = AzureARMHandler.objects.get(id=resource.azure_rh_id)
    
    cf_values_dict = resource.get_cf_values_as_dict()
    
    # get sub-resource object
    sb_resource = Resource.objects.get(parent_resource=resource, lifecycle="ACTIVE", id="{{dbs_cluster_id}}")
    
    # delete databricks clusters
    _delete_databricks_cluster(rh, cf_values_dict['workspace_name'], cf_values_dict['resource_group'], cf_values_dict['azure_dbs_workspace_url'], sb_resource)
    

    return "SUCCESS", "Databricks workspace cluster deleted successfully", ""