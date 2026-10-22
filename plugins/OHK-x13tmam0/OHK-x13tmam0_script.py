"""
Build service item action for AKS Cluster Deployment

This action uses an ARM Template to create an AKS Cluster
"""
import requests
import json
import time

from azure.mgmt.containerservice import ContainerServiceClient
from azure.mgmt.containerservice.models import ManagedCluster, ContainerServiceLinuxProfile, ManagedClusterAgentPoolProfile,ManagedClusterServicePrincipalProfile, ManagedClusterIdentity, ManagedClusterSKU, \
    ManagedClusterAPIServerAccessProfile

from accounts.models import Group
from containerorchestrators.models import ContainerOrchestratorTechnology
from containerorchestrators.kuberneteshandler.models import Kubernetes
from infrastructure.models import CustomField
from infrastructure.models import Environment
from common.methods import set_progress
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)


def generate_options_for_env_id(**kwargs):
    group_name = kwargs["group"]
    try:
        group = Group.objects.get(name=group_name)
    except:
        return []

    envs = group.get_available_environments()

    options = [(env.id, env.name) for env in envs if env.resource_handler.resource_technology.name == "Azure"]
    
    options.insert(0, ('', '--- First, Select an Environment ---'))
    
    return options


def generate_options_for_resource_group(field, control_value=None, **kwargs):
    options = []

    if not control_value:
        # options.append(('', '--- First, Select an Environment ---'))
        return options

    
    env = Environment.objects.get(id=control_value)

    groups = env.custom_field_options.filter(field__name='resource_group_arm')
    
    options = [(g.str_value, g.str_value) for g in groups]
    options = sorted(options, key=lambda tup: tup[1].lower())
    
    return options


def generate_options_for_node_size(field, control_value=None, **kwargs):
    options = []
    
    if not control_value:
        # options = [('', '--- First, Select an Environment ---')]
        return options

    env = Environment.objects.get(id=control_value)
    
    options = [(opt.value, opt.value) for opt in env.get_cfvs_for_custom_field('node_size')]
    options = sorted(options, key=lambda tup: tup[1].lower())
    
    if ('Standard_B4ms', 'Standard_B4ms') in options:
        return {'options': options, 'initial_value': ('Standard_B4ms', 'Standard_B4ms')}
    
    return options


def generate_options_for_kubernetes_version(field, control_value=None, **kwargs):
    options = []
    
    if control_value is None or control_value == "":
        # options = [('', '--- First, Select an Environment ---')]
        return options
    
    env = Environment.objects.get(id=control_value)
    rh = env.resource_handler.cast()
    wrapper = rh.get_api_wrapper()
    
    # get resource handler subscription id
    subscriptionId = wrapper.resource_client.azure_wrapper.subscription_id
    
    location = env.get_cf_values_as_dict()['node_location']
    resource_type = 'managedClusters'
    
    base_url = "https://management.azure.com/subscriptions"

    # rest api
    api_url = f'{subscriptionId}/providers/Microsoft.ContainerService/locations/{location}/orchestrators'
    query_param = f"api-version=2019-08-01&resource-type={resource_type}"
    access_token = wrapper.resource_client.azure_wrapper.credentials.get_token("https://management.core.windows.net/.default")
    headers = {
        'Authorization': f'Bearer {access_token.token}'
    }
    
    # Gets a list of supported orchestrators in the specified subscription. The operation returns properties of each orchestrator 
    # including version, available upgrades and whether that version or upgrades are in preview.
    # https://docs.microsoft.com/en-us/rest/api/aks/container-services/list-orchestrators
    response = requests.request("GET", f"{base_url}/{api_url}?{query_param}", headers=headers, data={})
    
    if response.status_code != 200:
        raise RuntimeError(f"Does not exist kebernetes version for selected region: {location}")
        
    default_option = None

    
    for k_obj in response.json()['properties']['orchestrators']:
        options.append((k_obj['orchestratorVersion'], k_obj['orchestratorVersion']))
    
        if "default" in k_obj and k_obj['default']:
            default_option = (k_obj['orchestratorVersion'], k_obj['orchestratorVersion'])
    
    options = sorted(options, key=lambda tup: tup[1].lower(), reverse=True)
    
    if default_option is not None:
        return {'options': options, 'initial_value': default_option}
    
    return options

def generate_options_for_sku_tier(**kwargs):
    return [("Paid", "Paid"), ("Free", "Free")]
    
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
    

def fetch_group_and_resource_handler_tags_dict(rh, group):
    # Get Tags from Group and Resource Handler. If matching attrs exist on
    # the resource then include them as tags
    tags = rh.taggableattribute_set.all()
    tags_to_apply = {}
    
    # Grab tags from the Group level first. Only applies params if a single
    # value is set for the group, and the param is required
    for tag in tags:
        tag_attribute = tag.attribute
        tag_name = tag.label
        
        cfvs = group.get_cfvs_for_custom_field(tag_attribute)
        
        if cfvs is not None:
            if len(cfvs) == 1:
        
                cf = group.custom_fields.get(name=tag_attribute)
        
                if cf.required:
                    tag_value = cfvs.first().value
        
                    if tag_value is not None:
                        tags_to_apply[tag_name] = f'{tag_value}'

    # Then grab tags from the Resource (these would overwrite Group level)
    for tag in tags:
        tag_attribute = tag.attribute
        tag_name = tag.label
        eval_str = f'resource.{tag_attribute}'
        
        try:
            tag_value = eval(eval_str)
        except AttributeError:
            continue
        
        if tag_value is not None:
            tags_to_apply[tag_name] = f'{tag_value}'
    
    return tags_to_apply

def _azure_aks_model_to_dict(cluster, rh, rg_name):
    model_dict = {
        'name': f'{cluster.name}',
        'azure_rh_id': rh.id,
        'resource_group': rg_name,
        'azure_location': cluster.location,
        'dns_prefix': cluster.dns_prefix,
        'enable_rbac': cluster.enable_rbac,
        'kubernetes_version': cluster.kubernetes_version,
        'azure_resource_id': cluster.id,
        'node_count': cluster.agent_pool_profiles[0].count,
        'os_disk_size': cluster.agent_pool_profiles[ 0].os_disk_size_gb,
        'node_size': cluster.agent_pool_profiles[0].vm_size,
        "power_state": getattr(getattr(cluster, "power_state", None), "code", None),
        # docker_bridge_cidr removed from network_profile in newer AKS API / SDK versions
        "docker_bridge_cidr": (
            getattr(cluster.network_profile, "docker_bridge_cidr", None)
            if getattr(cluster, "network_profile", None)
            else None
        ),
    }
    
    if cluster.fqdn is not None:
        model_dict["api_server_address"] =  cluster.fqdn
    else:
        model_dict["api_server_address"] =  cluster.private_fqdn

    try:
        model_dict["enable_azure_policy"] = cluster.addon_profiles.get('azurepolicy').enabled
    except AttributeError:
        pass
    
    try:
        model_dict["http_application_routing"] = cluster.addon_profiles.get('httpApplicationRouting').enabled
    except AttributeError:
        pass
    
    try:
        model_dict["enable_private_cluster"] = cluster.api_server_access_profile.enable_private_cluster
    except AttributeError:
        pass
    
    return model_dict
    
def _create_aks_kubernetes_cluster(rh, wrapper, resource_group, parameters, resource_name):
    
    # create container client object
    container_client = ContainerServiceClient(wrapper.credentials, rh.serviceaccount)
    
    try:
        # create kubernetes cluster
        resp = container_client.managed_clusters.begin_create_or_update(resource_group, resource_name, parameters)
        # Need to wait for each create to complete in case there are
        # resources dependent on others (VM disks, etc.)
        resp = resp.result()
    except Exception as err:
        raise RuntimeError(f"Unexpected exception occurred: {err}")
    
    return resp 

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
    
    
def run(job, **kwargs):
    resource = kwargs.get('resource')
    
    set_progress(f"Started provisioning of kubernetes cluster for: {resource}")
    logger.info(f"Started provisioning of kubernetes cluster for: {resource}")
    
    # get or create custom fields if it does not exist
    get_or_create_cfs()
    
    env_id = "{{env_id}}"
    resource_group = "{{resource_group}}"

    env = Environment.objects.get(id=env_id)
    rh = env.resource_handler.cast()
    wrapper = rh.get_api_wrapper()
    deployment_name = "{{cluster_name}}" # format name as per rules https://aka.ms/aks-naming-rules
    kubernetes_version="{{kubernetes_version}}"

    # create cluster input param
    parameters = ManagedCluster(
        location=env.node_location,
        dns_prefix=f"{deployment_name}-dns",
        kubernetes_version=kubernetes_version,
        tags=fetch_group_and_resource_handler_tags_dict(rh, resource.group),
        service_principal_profile=ManagedClusterServicePrincipalProfile(client_id=rh.client_id, secret=rh.secret),
        agent_pool_profiles=[ManagedClusterAgentPoolProfile(name="agentpool",
                                                            vm_size="{{node_size}}",
                                                            os_disk_size_gb= int("{{os_disk_size}}"),
                                                            count=int("{{node_count}}"),
                                                            os_type="Linux",
                                                            min_count=1,
                                                            max_count=50,
                                                            type="VirtualMachineScaleSets",
                                                            mode="System",
                                                            max_pods=100,
                                                            availability_zones=[1,2,3],
                                                            enable_node_public_ip=True,
                                                            orchestrator_version=kubernetes_version,
                                                            enable_auto_scaling=True)], 
        enable_rbac=json.loads("{{enable_rbac}}".lower()),
        addon_profiles = None,
        identity=ManagedClusterIdentity(
                type="SystemAssigned"
            ),
        sku= ManagedClusterSKU(
                name="Base",
                tier="{{sku_tier}}"
            ),
        api_server_access_profile=ManagedClusterAPIServerAccessProfile(enable_private_cluster=json.loads("{{enable_private_cluster}}".lower()))
    )
    

    # create kubernetes cluster
    aks_resp = _create_aks_kubernetes_cluster(rh, wrapper, resource_group, parameters, deployment_name)

    set_progress(f'Azure Kebernetes cluster created successfully')
    logger.info(f"Azure kubernetes cluster resp: {aks_resp}")
    
    # convert model object to dict
    ask_dict = _azure_aks_model_to_dict(aks_resp, rh, resource_group)
    
    tech = ContainerOrchestratorTechnology.objects.get(name='Kubernetes')
    kubernetes = Kubernetes.objects.create(
        name=deployment_name,
        ip=ask_dict['api_server_address'],
        port=443,
        protocol='https',
        auth_type='TOKEN',
        servicepasswd=_get_cluster_bearer_token(rh, wrapper, resource_group, deployment_name),
        container_technology=tech,
        environment=env,
    )
    resource.container_orchestrator_id = kubernetes.id
    
    for key, value in ask_dict.items():
        setattr(resource, key, value) # set custom field value
        
    resource.save()
    
    # create a new Environment for the new container orchestrator
    Environment.objects.create(name="Resource-{} Environment".format(resource.id), container_orchestrator=kubernetes)
    
    return "SUCCESS", "Azure Kebernetes created successfully", ""