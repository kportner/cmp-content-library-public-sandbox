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
from utilities.logger import ThreadLogger
from resources.models import Resource, ResourceType

logger = ThreadLogger(__name__)


"""
Todo - Pending feature
1. Create Job
2. Create Table
3. Create Notebook
API reference - https://docs.microsoft.com/en-gb/azure/databricks/dev-tools/api/latest/
"""


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
            'label': "Databricks Runtime Version",
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

def _get_databricks_header_and_url(rh, dbricks_workspace, resource_group):
    
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
    
    return dbricks_auth 


def create_databricks_cluster(rh, resource_group, dbricks_workspace, dbricks_location, cluster_kwargs, count=0):
    '''
    Create databricks workspace cluster
    '''
    
    dbricks_auth = _get_databricks_header_and_url(rh, dbricks_workspace, resource_group)
    
    # create databricks workspace cluster
    ds_rsp = requests.post(f"{dbricks_location}/api/2.0/clusters/create", headers=dbricks_auth, data=json.dumps(cluster_kwargs))
    result = ds_rsp.json()
    
    if ds_rsp.status_code == 200:
        return result
        
    logger.info("Got this error when creating a cluster after creating a workspace : %s", result)
    
    if count < 2:
        logger.info("Databricks cluster params %s", cluster_kwargs)
        
        # system got UnknownWorkerEnvironmentException when creating a cluster after creating a workspace
        # https://github.com/databrickslabs/terraform-provider-databricks/issues/33
        time.sleep(600)
        
        logger.info("retry to create cluster after 600 seconds sleep")
        
        # retry create databricks cluster
        create_databricks_cluster(rh, resource_group, dbricks_workspace, dbricks_location, cluster_kwargs, count+1)

    raise RuntimeError(result) 


def get_databricks_cluster(rh, resource_group, dbricks_workspace, dbricks_location, cluster_kwargs):
    dbricks_auth = _get_databricks_header_and_url(rh, dbricks_workspace, resource_group)
    
    # get databricks workspace cluster
    ds_rsp = requests.post(f"{dbricks_location}/api/2.0/clusters/get", headers=dbricks_auth, data=json.dumps(cluster_kwargs))
    result = ds_rsp.json()
    
    if ds_rsp.status_code != 200:
        raise RuntimeError(result)
    
    return result
        
def _request_client(resource, api_end_point_uri):
    cf_values_dict = resource.get_cf_values_as_dict()
    
    # get resource handler object
    rh = AzureARMHandler.objects.get(id=cf_values_dict['azure_rh_id'])
    
    dbricks_auth = _get_databricks_header_and_url(rh, cf_values_dict['workspace_name'], cf_values_dict['resource_group'])
    
    # fetch databricks workspace cluster spark-versions
    ds_rsp = requests.get(f"{cf_values_dict['azure_dbs_workspace_url']}/api/2.0/clusters/{api_end_point_uri}", headers=dbricks_auth)
    result = ds_rsp.json()
    
    if ds_rsp.status_code != 200:
        raise RuntimeError(result)
    
    return result
        
def generate_options_for_dbs_runtime_version(field, **kwargs):
    """
    Return databricks runtime version
    """
    resource = kwargs.get("resource", None)
    
    if resource is None:
        return []
    
    # fetch spark versions list
    result = _request_client(resource, "spark-versions")
    
    options = [(xx['key'], xx['name']) for xx in result['versions']]
    
    return options


def generate_options_for_dbs_worker_type(field, **kwargs):
    """
    Return node type
    """
    resource = kwargs.get("resource", None)
    
    if resource is None:
        return []
    
    # fetch node type list list
    result = _request_client(resource, "list-node-types")
    
    options = [(xx['node_type_id'], "{0} ({1}, {2} GB Memory, {3} Cores) ".format(xx['category'], xx['node_type_id'], int(xx['memory_mb']/1024), int(xx['num_cores']))) for xx in result['node_types']]
    
    return options


def run(job, *args, **kwargs):
    set_progress("Starting Provision of the databricks workspace cluster...")
    logger.info("Starting Provision of the databricks workspace cluster...")
    
    resource = kwargs.get('resource')
    
    # get or create resource type and create custom fields if not exists
    resource_type = get_or_create_custom_fields()
    
    create_cluster_params = {
        'cluster_name': '{{dbs_cluster_name}}', # free text
        'spark_version': '{{dbs_runtime_version}}', # drop down, show/hide based on cluster_name field value
        'node_type_id': '{{dbs_worker_type}}', # drop down, show/hide based on cluster_name field value
        'num_workers': '{{dbs_num_workers}}', # int, show/hide based on cluster_name field value, min=2
        'autotermination_minutes':  '{{autotermination_minutes}}', # int, show/hide based on cluster_name field value, min=10 and max=10000
        "spark_conf": {
            "spark.speculation": True
        }
    }
    
    logger.info("Databricks worspace cluster params : %s", create_cluster_params)
    
    # get resource handler object
    rh = AzureARMHandler.objects.get(id=resource.azure_rh_id)
    
    # deploy databricks workspace cluster
    clust_resp = create_databricks_cluster(rh, resource.resource_group, resource.name, resource.azure_dbs_workspace_url, create_cluster_params)
    
    logger.info("Databricks worspace cluster response 1 : %s", clust_resp)
    
    time.sleep(120)
    
    # fetch databricks cluster
    clust_resp = get_databricks_cluster(rh, resource.resource_group, resource.name, resource.azure_dbs_workspace_url, clust_resp)
    
    logger.info("Databricks worspace cluster response 2 : %s", clust_resp)
    
    # create databricks cluster as a sub resource of blueprint
    res = Resource.objects.create(group=resource.group, parent_resource=resource, resource_type=resource_type, 
                        name=create_cluster_params['cluster_name'], 
                        blueprint=resource.blueprint, lifecycle="ACTIVE")

    res.dbs_cluster_state = clust_resp.get("state", "")
    res.dbs_cluster_id = clust_resp.get("cluster_id", "")
    res.dbs_cluster_name = clust_resp.get("cluster_name", "")
    res.dbs_runtime_version = clust_resp.get("spark_version", "")
    res.dbs_worker_type = clust_resp.get("node_type_id", "")
    res.dbs_num_workers = clust_resp.get("num_workers", "")
    res.autotermination_minutes = clust_resp.get("autotermination_minutes", "")
    res.save()
        

    return "SUCCESS", "Databricks workspace cluster deployed successfully", ""