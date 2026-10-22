"""
Discover Azure Resource groups and clusters
Return Azure Resource groups and clusters identified by sku, handler_id and
location
"""
from datetime import datetime

from azure.common.credentials import ServicePrincipalCredentials
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.containerservice import ContainerServiceClient

from accounts.models import Group
from resourcehandlers.azure_arm.models import AzureARMHandler
from containerorchestrators.models import ContainerOrchestratorTechnology
from containerorchestrators.kuberneteshandler.models import Kubernetes
from infrastructure.models import Environment, CustomField
from servicecatalog.models import ServiceBlueprint
from resources.models import Resource, ResourceType
from common.methods import set_progress
from utilities.logger import ThreadLogger


logger = ThreadLogger(__name__)


RESOURCE_IDENTIFIER = 'azure_resource_id'

def create_cf(cf_name, cf_label, description, cf_type="STR", required=False, **kwargs):
    defaults = {
        'label': cf_label,
        'description': description,
        'required': required,
    }
    
    for key, value in kwargs.items():
        defaults[key] = value

    CustomField.objects.get_or_create(
        name=cf_name,
        type=cf_type,
        defaults=defaults
    )


def get_or_create_cfs():
    create_cf('azure_rh_id', 'Azure RH ID', 'Used by the Azure blueprints')
    create_cf('azure_region', 'Azure Region', 'Used by the Azure blueprints')
    create_cf('azure_resource_id', 'Kuernetes Resource ID', 'Kubernetes Resource ID')
    create_cf('node_size', 'Node Size', 'Size of the Nodes in the cluster')
    create_cf('node_count', 'Node Count', 'How many nodes to deploy for the cluster', cf_type="INT")
    create_cf('os_disk_size', 'OS Disk Size', 'Disk size (in GiB) to provision for each of the agent pool nodes. This value ranges from 0 to 1023. Specifying 0 will apply the default disk size for that agentVMSize', cf_type="INT")
    create_cf('kubernetes_version', 'Kubernetes Version', 'The version of Kubernetes', show_on_servers=True)
    create_cf('dns_prefix', 'Dns Prefix', 'DNS prefix to use with hosted Kubernetes API server FQDN')
    create_cf('enable_rbac', 'Enable Rbac', 'Boolean flag to turn on and off of RBAC', cf_type="BOOL")
    create_cf('enable_private_cluster', 'Enable Private Cluster', 'Enable private network access to the Kubernetes cluster', cf_type="BOOL")
    create_cf('http_application_routing', 'Http Application Routing', 'Boolean flag to turn on and off http application routing', cf_type="BOOL")
    create_cf('enable_azure_policy', 'Enable Azure Policy', 'Boolean flag to turn on and off Azure Policy addon', cf_type="BOOL")
    create_cf('power_state', 'Power State', 'Power State, to turn ON/OFF machine', show_on_servers=True)
    create_cf('api_server_address', 'API server address', 'API server address', show_on_servers=True)
    create_cf('docker_bridge_cidr', 'Docker bridge CIDR', 'Docker bridge CIDR', show_on_servers=True)
    create_cf('container_orchestrator_id', 'Container Orchestrator ID', 'Container Orchestrator ID', cf_type="INT")


def _get_cluster_bearer_token(rh, wrapper, rg_name, rs_name):
    
    # create container client object
    container_client = ContainerServiceClient(wrapper.credentials, rh.serviceaccount)
    
    # fetch admin credential
    kubeconfig = container_client.managed_clusters.list_cluster_admin_credentials(rg_name, rs_name)
    
    aks_credentials = {}
    
    for xx in kubeconfig.kubeconfigs[0].value.decode().split("\n"):
        s = xx.split(":")
        aks_credentials[s[0].strip()] = s[1].strip() if len(s) > 1 else ""
    
    return aks_credentials.get("token", "NA")
    
def discover_resources(**kwargs):
    discovered_clusters = []
    created, updated = 0, 0
    
    # get or create custom fields if it does not exist
    get_or_create_cfs()
    
    group = Group.objects.filter(name__icontains='unassigned').first()
    blueprint = ServiceBlueprint.objects.filter(name__icontains="Azure Kubernetes Service").first()
    resource_type = ResourceType.objects.filter(name__icontains="kubernetes_cluster").first()
    
    for rh in AzureARMHandler.objects.all():
        
        set_progress('Connecting to Azure Resource Group for handler: {}'.format(rh))
        
        wrapper = rh.get_api_wrapper()
        credentials = wrapper.credentials
        resource_client = ResourceManagementClient(credentials, rh.serviceaccount)
        container_client = ContainerServiceClient(credentials, rh.serviceaccount)
        
        for rg in list(resource_client.resource_groups.list()):
            for cluster in list(container_client.managed_clusters.list_by_resource_group(resource_group_name=rg.name)):
                
                # fetch environment object
                env = Environment.objects.filter(resource_handler__resource_technology__name="Azure", node_location=cluster.location).first()
                
                if env is None:
                    continue
                
                set_progress(f'Discovered aks cluster name: {cluster.name}')
                
                discovered_cluster = {
                    'name': f'{cluster.name}',
                    'azure_rh_id': rh.id,
                    'resource_group': rg.name,
                    'azure_location': cluster.location,
                    'dns_prefix': cluster.dns_prefix,
                    'enable_rbac': cluster.enable_rbac,
                    'kubernetes_version': cluster.kubernetes_version,
                    'last_synced': datetime.now(),
                    'synced_from_system': True,
                    'azure_resource_id': cluster.id,
                    'node_count': cluster.agent_pool_profiles[0].count,
                    'os_disk_size': cluster.agent_pool_profiles[ 0].os_disk_size_gb,
                    'node_size': cluster.agent_pool_profiles[0].vm_size,
                    "power_state": cluster.power_state.code,
                    "docker_bridge_cidr": cluster.network_profile.docker_bridge_cidr,
                    
                }
                
                if cluster.fqdn is not None:
                    discovered_cluster['api_server_address'] = cluster.fqdn
                else:
                    discovered_cluster['api_server_address'] = cluster.private_fqdn
                    
                try:
                    discovered_cluster["enable_azure_policy"] = cluster.addon_profiles.get('azurepolicy').enabled
                except AttributeError:
                    pass
                
                try:
                    discovered_cluster["http_application_routing"] = cluster.addon_profiles.get('httpApplicationRouting').enabled
                except AttributeError:
                    pass
                
                try:
                    discovered_cluster["enable_private_cluster"] = cluster.api_server_access_profile.enable_private_cluster
                except AttributeError:
                    pass
                
                logger.info(f'discovered cluster: {discovered_cluster}')
                
                resource = Resource.objects.filter(name__exact = discovered_cluster['name'], lifecycle = 'ACTIVE').first()
                
                if not resource:
                    resource = Resource.objects.create(
                        name=discovered_cluster['name'],
                        blueprint=blueprint,
                        group=group,
                        resource_type=resource_type,
                        lifecycle = 'ACTIVE'
                    )
                    
                    tech = ContainerOrchestratorTechnology.objects.get(name='Kubernetes')
                    
                    kubernetes = Kubernetes.objects.create(
                        name=discovered_cluster['name'],
                        ip=discovered_cluster['api_server_address'],
                        port=443,
                        protocol='https',
                        auth_type='TOKEN',
                        servicepasswd=_get_cluster_bearer_token(rh, rh.get_api_wrapper(), rg.name, discovered_cluster['name']),
                        container_technology=tech,
                        environment=env,
                    )
                    
                    resource.container_orchestrator_id = kubernetes.id
                    
                    # create a new Environment for the new container orchestrator
                    Environment.objects.create(name="Resource-{} Environment".format(resource.id), container_orchestrator=kubernetes)
                    
                    created +=1
                    
                else:
                    updated +=1
                
                for key, value in discovered_cluster.items():
                    setattr(resource, key, value) # set custom field value
                
                resource.save()
                
    set_progress(f'Azure Kubernetes Service BP discovered {created+updated} resources where {created} created and {updated} updated.')
    
    return []