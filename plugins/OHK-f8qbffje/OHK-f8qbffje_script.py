"""
This is a working sample CloudBolt plug-in for you to start with. The run method is required,
but you can change all the code within it. See the "CloudBolt Plug-ins" section of the docs for
more info and the CloudBolt forge for more examples:
https://github.com/CloudBoltSoftware/cloudbolt-forge/tree/master/actions/cloudbolt_plugins
"""
import requests
import json
import time
from common.methods import set_progress
from infrastructure.models import CustomField
from resourcehandlers.azure_arm.models import AzureARMHandler
from resources.models import Resource, ResourceType
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)


def get_or_create_custom_fields():
    """ 
    Get or create a new custom fields
    """
    CustomField.objects.get_or_create(
        name="dbs_cluster_name",
        type="STR",
        defaults={
            'label': "Cluster Name",
            'description': 'Used by the ARM Template blueprint.',
            'required': True,
        }
    )
    
    CustomField.objects.get_or_create(
        name="dbs_runtime_version",
        type="STR",
        defaults={
            'label': "Cluster Runtime Version",
            'description': 'Selects the image that will be used to create the cluster. For details about specific images, see the Databricks Guide.',
            'required': True,
            "show_on_servers": True
        }
    )
    
    CustomField.objects.get_or_create(
        name="dbs_worker_type",
        type="STR",
        defaults={
            'label': "Worker Type",
            'description': 'Databricks recommends Delta Cache Accelerated (Storage Optimized) worker types as they have accelerated data access through Delta caching.',
            'required': True,
            "show_on_servers": True
        }
    )
    
    CustomField.objects.get_or_create(
        name="dbs_num_workers",
        type="INT",
        defaults={
            'label': "Number Workes",
            'description': 'Interval must be between 1 and 120 numbers',
            'required': True,
        }
    )
    
    CustomField.objects.get_or_create(
        name="autotermination_minutes",
        type="INT",
        defaults={
            'label': "Terminate After",
            'description': 'the cluster will terminate after the specified time interval of inactivity (i.e., no running commands or active job runs). This feature is best supported in the latest Spark versions.Interval must be between 10 and 10000 minutes',
            'required': True,
        }
    )
    
    CustomField.objects.get_or_create(
        name="dbs_cluster_id",
        type="STR",
        defaults={
            'label': "Cluster ID",
            'description': 'Databricks Cluster ID',
            'required': False,
            "show_on_servers": True
        }
    )
    
    CustomField.objects.get_or_create(
        name="dbs_cluster_state",
        type="STR",
        defaults={
            'label': "Cluster State",
            'description': 'Databricks Cluster STATE',
            'required': False,
            "show_on_servers": True
        }
    )
    
    # get or create resource type
    rt, _ = ResourceType.objects.get_or_create(
        name="databricks_cluster",
        defaults={"label": "Databricks Cluster", "icon": "far fa-file"}
    )
    
    return rt
    
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

def create_databricks_cluster_cb_subresource(resource, resource_type, cluster):
    """
    Create databricks cluster
    params: resource : resource object
    params: resource : resource_type object
    params: cluster : databricks cluster object 
    """
    
    # create databricks cluster as a sub resource of blueprint
    res = Resource.objects.create(group=resource.group, parent_resource=resource, resource_type=resource_type, name=cluster['dbs_cluster_name'], 
                        blueprint=resource.blueprint, lifecycle="ACTIVE")
    
    for key, value in cluster.items():
        setattr(res, key, value) # set custom field value

    res.save()
    
    logger.info(f'Sub Reousce {res} created successfully.')
    
def _sync_databricks_clusters(rh, dbricks_workspace, resource_group, databricks_workspace_url, resource_type, resource):
    
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
    
    # fetch databricks workspace cluster list
    ds_rsp = requests.get(f"{databricks_workspace_url}/api/2.0/clusters/list", headers=dbricks_auth)
    result = ds_rsp.json()
    
    if ds_rsp.status_code != 200:
        raise RuntimeError(result) 
    
    if not result:
        return []
        
    discovered_objects = []
    
    # get all sub resource objects
    sub_resources = Resource.objects.filter(parent_resource=resource, resource_type=resource_type, lifecycle="ACTIVE")
    
    
    for clusterObj in result['clusters']:
    
        cluster_dict = {
                'dbs_cluster_name': clusterObj['cluster_name'],
                'dbs_runtime_version': clusterObj['spark_version'],
                'dbs_cluster_id': clusterObj['cluster_id'],
                'dbs_worker_type': clusterObj['node_type_id'],
                'autotermination_minutes': clusterObj['autotermination_minutes'],
                'dbs_cluster_state': clusterObj['state']
            }
            
        discovered_objects.append(cluster_dict)
        
        # search databricks cluster name in cb resource
        res = sub_resources.filter(name=clusterObj['cluster_name']).first()
        
        if not res:
            set_progress("Found new databricks cluster '{0}', creating sub-resource...".format(clusterObj['cluster_name']))
            
            # create databricks cluster cb resource
            create_databricks_cluster_cb_subresource(resource, resource_type, cluster_dict)
    
    return discovered_objects
        
def run(job, *args, **kwargs):
    set_progress("Syncing databricks workspace cluster...")
    logger.info("Syncing databricks workspace cluster...")
    
    resource = kwargs.get('resource')
    
    # get or create resource type object and create custom fields if not exists
    resource_type= get_or_create_custom_fields()
    
    # get resource handler object
    rh = AzureARMHandler.objects.get(id=resource.azure_rh_id)
    
    cf_values_dict = resource.get_cf_values_as_dict()
    
    # sync databricks clusters
    clusters = _sync_databricks_clusters(rh, cf_values_dict['workspace_name'], cf_values_dict['resource_group'], cf_values_dict['azure_dbs_workspace_url'], resource_type, resource)
    
    logger.info(f'Databricks clusters:  {clusters}')
    
    return "SUCCESS", "Databricks workspace cluster synced successfully", ""