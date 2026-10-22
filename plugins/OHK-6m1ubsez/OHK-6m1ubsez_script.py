"""
This is a working sample CloudBolt plug-in for you to start with. The run method is required,
but you can change all the code within it. See the "CloudBolt Plug-ins" section of the docs for
more info and the CloudBolt forge for more examples:
https://github.com/CloudBoltSoftware/cloudbolt-forge/tree/master/actions/cloudbolt_plugins
"""
from common.methods import set_progress
from containerorchestrators.kuberneteshandler.models import Kubernetes
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)


def delete_namespace(wrapper, base_url, namespace_name):
    url = f"{base_url}/api/v1/namespaces"
    rsp = wrapper.requests_delete("{0}/{1}".format(url, namespace_name))
    logger.info(f"Namespace response: {rsp.json()}")


def delete_cluster_role_binding(wrapper, cluster_role_binding_name):
    url = wrapper.get_clusterrole_url(
        version="rbac.authorization.k8s.io/v1/clusterrolebindings"
    )
    rsp = wrapper.requests_delete("{0}/{1}".format(url, cluster_role_binding_name))
    logger.info(f"cluster role binding response: {rsp.json()}")


def delete_cluster_role(wrapper, cluster_role_name):
    url = wrapper.get_clusterrole_url(
        version="rbac.authorization.k8s.io/v1/clusterroles"
    )
    rsp = wrapper.requests_delete("{0}/{1}".format(url, cluster_role_name))
    logger.info(f"cluster role response: {rsp.json()}")


def run(job, resource, *args, **kwargs):
    set_progress(f"Prometheus portal delete plugin running for resource: {resource}")
    logger.info(
        f"Prometheus portal delete plugin running for resource: {resource.name}"
    )

    cf_value = resource.get_cf_values_as_dict()

    namespace = cf_value.get("prometheus_namespace", None)
    cluster_role_name = cf_value.get("cluster_role_name", None)
    cluster_role_binding_name = cf_value.get("cluster_role_binding_name", None)
    container_orchestrator_id = cf_value.get("container_orchestrator_id", None)

    if (
        not namespace
        or not cluster_role_name
        or not cluster_role_binding_name
        or not container_orchestrator_id
    ):
        return (
            "SUCCESS",
            "Prometheus portal '{0}' deleted successfully".format(resource.name),
            "",
        )

    oc_handler = Kubernetes.objects.get(id=container_orchestrator_id)

    base_url = "{0}://{1}:{2}".format(
        oc_handler.protocol, oc_handler.ip, oc_handler.port
    )

    wrapper = oc_handler.cast().get_api_wrapper()

    try:
        delete_cluster_role_binding(wrapper, cluster_role_binding_name)
        delete_cluster_role(wrapper, cluster_role_name)
        delete_namespace(wrapper, base_url, namespace)
    except Exception as err:
        logger.error(err)
        return "FAILURE", f"{err}", ""
    
    oc_handler.prometheus_url = None
    oc_handler.save()
    
    try:
        # sync namespaces
        oc_handler.sync_resource_metadata(sync_resource_type="sync_namespaces")
        # sync deployments
        oc_handler.sync_resource_metadata(sync_resource_type="sync_deployments")
        # sync nodes
        oc_handler.sync_resource_metadata(sync_resource_type="sync_nodes")
        # sync pods
        oc_handler.sync_resource_metadata(sync_resource_type="sync_pods")
    except Exception as err:
        pass
    
    return (
        "SUCCESS",
        "Prometheus portal '{0}' deleted successfully".format(resource.name),
        "",
    )