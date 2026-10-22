"""
This is a working sample CloudBolt plug-in for you to start with. The run method is required,
but you can change all the code within it. See the "CloudBolt Plug-ins" section of the docs for
more info and the CloudBolt forge for more examples:
https://github.com/CloudBoltSoftware/cloudbolt-forge/tree/master/actions/cloudbolt_plugins
"""
import json
import time
from infrastructure.models import CustomField
from containerorchestrators.kuberneteshandler.models import Kubernetes

from common.methods import set_progress
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)


def get_or_create_custom_fields():
    """
    Helper functions for main function to create custom field as needed
    """
    CustomField.objects.get_or_create(
        name="container_orchestrator_id",
        defaults={
            "label": "Container Orchestrator",
            "type": "INT",
            "show_as_attribute": True,
        },
    )

    CustomField.objects.get_or_create(
        name="prometheus_url",
        defaults={
            "label": "Prometheus URL",
            "type": "URL",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )

    CustomField.objects.get_or_create(
        name="prometheus_port",
        defaults={"label": "Prometheus Port", "type": "INT", "required": True},
    )

    CustomField.objects.get_or_create(
        name="prometheus_namespace",
        defaults={
            "label": "Prometheus Namespace",
            "type": "STR",
            "show_as_attribute": True,
        },
    )

    CustomField.objects.get_or_create(
        name="cluster_role_name",
        defaults={
            "label": "Cluster Role Name",
            "type": "STR",
            "show_as_attribute": True,
        },
    )

    CustomField.objects.get_or_create(
        name="cluster_role_binding_name",
        defaults={
            "label": "Cluster Role Binding Name",
            "type": "STR",
            "show_as_attribute": True,
        },
    )

    CustomField.objects.get_or_create(
        name="config_name",
        defaults={"label": "Configmap Name", "type": "STR", "show_as_attribute": True},
    )

    CustomField.objects.get_or_create(
        name="service_name",
        defaults={"label": "Service Name", "type": "STR", "show_as_attribute": True},
    )

    CustomField.objects.get_or_create(
        name="deployment_name",
        defaults={"label": "Deployment Name", "type": "STR", "show_as_attribute": True},
    )

    CustomField.objects.get_or_create(
        name="app_name",
        defaults={
            "label": "Application Group Name",
            "type": "STR",
            "show_as_attribute": True,
        },
    )


def generate_options_for_container_orchestrator_id(
    control_value=None, server=None, **kwargs
):
    options = [("", "---Select Container---")]
    for oc in Kubernetes.objects.all():
        options.append((oc.id, oc.name))
    return options


def _get_or_create_namespaces(wrapper, base_url, namespace_name):
    """
    Create a Kubernetes namespace
    """
    data = {
        "kind": "Namespace",
        "apiVersion": "v1",
        "metadata": {"name": namespace_name},
    }

    url = f"{base_url}/api/v1/namespaces"

    try:
        rsp = wrapper._send_request("{0}/{1}".format(url, namespace_name))
    except Exception as err:
        rsp = wrapper.requests_post(url, json=data)

    logger.info(f"Namespace response: {rsp.json()}")


def _create_cluster_role(wrapper, cluster_role_name="prometheus"):
    """
    Create a Kubernetes cluster role, so that users can access the resources
    """
    data = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRole",
        "metadata": {"name": cluster_role_name},
        "rules": [
            {
                "apiGroups": [""],
                "resources": [
                    "nodes",
                    "namespaces",
                    "pods",
                    "configmaps",
                    "endpoints",
                    "events",
                    "limitranges",
                    "persistentvolumeclaims",
                    "podtemplates",
                    "replicationcontrollers",
                    "resourcequotas",
                    "secrets",
                    "serviceaccounts",
                    "services",
                    "nodes/proxy",
                ],
                "verbs": ["get", "list", "watch"],
            },
            {
                "apiGroups": ["apps"],
                "resources": [
                    "deployments",
                    "daemonsets",
                    "statefulsets",
                    "replicasets",
                ],
                "verbs": ["get", "list"],
            },
            {
                "apiGroups": ["batch"],
                "resources": ["jobs", "cronjobs"],
                "verbs": ["get", "list"],
            },
            {
                "apiGroups": ["coordination.k8s.io"],
                "resources": ["leases"],
                "verbs": ["get", "list"],
            },
            {
                "apiGroups": ["discovery.k8s.io"],
                "resources": ["endpointslices"],
                "verbs": ["get", "list"],
            },
            {
                "apiGroups": ["events.k8s.io"],
                "resources": ["events"],
                "verbs": ["get", "list"],
            },
            {
                "apiGroups": ["extensions"],
                "resources": [
                    "daemonsets",
                    "deployments",
                    "ingresses",
                    "networkpolicies",
                    "replicasets",
                ],
                "verbs": ["get", "list", "watch"],
            },
            {
                "apiGroups": ["networking.k8s.io"],
                "resources": ["ingresses", "networkpolicies"],
                "verbs": ["get", "list"],
            },
            {
                "apiGroups": ["policy"],
                "resources": ["poddisruptionbudgets"],
                "verbs": ["get", "list"],
            },
            {
                "apiGroups": ["rbac.authorization.k8s.io"],
                "resources": ["rolebindings", "roles"],
                "verbs": ["get", "list"],
            },
            {
                "apiGroups": ["storage.k8s.io"],
                "resources": ["csistoragecapacities"],
                "verbs": ["get", "list"],
            },
            {
                "nonResourceURLs": ["/metrics"],
                "verbs": ["get"],
            },
        ],
    }

    url = wrapper.get_clusterrole_url(
        version="rbac.authorization.k8s.io/v1/clusterroles"
    )

    try:
        rsp = wrapper._send_request("{0}/{1}".format(url, cluster_role_name))
    except Exception as err:
        rsp = wrapper.requests_post(url, json=data)

    logger.info(f"cluster role response: {rsp.json()}")


def _create_cluster_role_binding(
    wrapper,
    namespace,
    cluster_role_name,
    cluster_role_binding_name="prometheus",
):
    """
    Create a Kubernetes cluster role bindings
    """
    url = wrapper.get_clusterrole_url(
        version="rbac.authorization.k8s.io/v1/clusterrolebindings"
    )

    data = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRoleBinding",
        "metadata": {"name": cluster_role_binding_name},
        "subjects": [
            {
                "kind": "ServiceAccount",
                "name": "default",
                "namespace": namespace,
            }
        ],
        "roleRef": {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "ClusterRole",
            "name": cluster_role_name,
        },
    }

    try:
        rsp = wrapper._send_request("{0}/{1}".format(url, cluster_role_binding_name))
    except Exception as err:
        rsp = wrapper.requests_post(url, json=data)

    logger.info(f"cluster role binding response: {rsp.json()}")


def _create_config_map(
    wrapper, base_url, namespace, config_name="prometheus-server-conf"
):
    data = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": config_name,
            "labels": {"name": config_name},
            "namespace": namespace,
        },
        "data": {
            "prometheus.rules": "groups:\n- name: UnixArena demo alert\n  rules:\n  - alert: High Pod Memory\n    expr: sum(container_memory_usage_bytes) > 1\n    for: 1m\n    labels:\n      severity: slack\n    annotations:\n      summary: High Memory Usage",
            "prometheus.yml": "global:\n  scrape_interval: 5s\n  evaluation_interval: 5s\nrule_files:\n  - /etc/prometheus/prometheus.rules\nalerting:\n  alertmanagers:\n  - scheme: http\n    static_configs:\n    - targets:\n      - \"alertmanager.monitoring.svc:9093\"\n\nscrape_configs:\n  - job_name: 'node-exporter'\n    kubernetes_sd_configs:\n      - role: endpoints\n    relabel_configs:\n    - source_labels: [__meta_kubernetes_endpoints_name]\n      regex: 'node-exporter'\n      action: keep\n\n  - job_name: 'kubernetes-apiservers'\n\n    kubernetes_sd_configs:\n    - role: endpoints\n    scheme: https\n\n    tls_config:\n      ca_file: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt\n    bearer_token_file: /var/run/secrets/kubernetes.io/serviceaccount/token\n\n    relabel_configs:\n    - source_labels: [__meta_kubernetes_namespace, __meta_kubernetes_service_name, __meta_kubernetes_endpoint_port_name]\n      action: keep\n      regex: default;kubernetes;https\n\n  - job_name: 'kubernetes-nodes'\n\n    scheme: https\n\n    tls_config:\n      ca_file: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt\n    bearer_token_file: /var/run/secrets/kubernetes.io/serviceaccount/token\n\n    kubernetes_sd_configs:\n    - role: node\n\n    relabel_configs:\n    - action: labelmap\n      regex: __meta_kubernetes_node_label_(.+)\n    - target_label: __address__\n      replacement: kubernetes.default.svc:443\n    - source_labels: [__meta_kubernetes_node_name]\n      regex: (.+)\n      target_label: __metrics_path__\n      replacement: /api/v1/nodes/${1}/proxy/metrics\n\n  - job_name: 'kubernetes-pods'\n\n    kubernetes_sd_configs:\n    - role: pod\n\n    relabel_configs:\n    - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]\n      action: keep\n      regex: true\n    - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_path]\n      action: replace\n      target_label: __metrics_path__\n      regex: (.+)\n    - source_labels: [__address__, __meta_kubernetes_pod_annotation_prometheus_io_port]\n      action: replace\n      regex: ([^:]+)(?::\\d+)?;(\\d+)\n      replacement: $1:$2\n      target_label: __address__\n    - action: labelmap\n      regex: __meta_kubernetes_pod_label_(.+)\n    - source_labels: [__meta_kubernetes_namespace]\n      action: replace\n      target_label: kubernetes_namespace\n    - source_labels: [__meta_kubernetes_pod_name]\n      action: replace\n      target_label: kubernetes_pod_name\n\n  - job_name: 'kube-state-metrics'\n    static_configs:\n      - targets: ['kube-state-metrics.kube-system.svc.cluster.local:8080']\n\n  - job_name: 'kubernetes-cadvisor'\n\n    scheme: https\n\n    tls_config:\n      ca_file: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt\n    bearer_token_file: /var/run/secrets/kubernetes.io/serviceaccount/token\n\n    kubernetes_sd_configs:\n    - role: node\n\n    relabel_configs:\n    - action: labelmap\n      regex: __meta_kubernetes_node_label_(.+)\n    - target_label: __address__\n      replacement: kubernetes.default.svc:443\n    - source_labels: [__meta_kubernetes_node_name]\n      regex: (.+)\n      target_label: __metrics_path__\n      replacement: /api/v1/nodes/${1}/proxy/metrics/cadvisor\n\n  - job_name: 'kubernetes-service-endpoints'\n\n    kubernetes_sd_configs:\n    - role: endpoints\n\n    relabel_configs:\n    - source_labels: [__meta_kubernetes_service_annotation_prometheus_io_scrape]\n      action: keep\n      regex: true\n    - source_labels: [__meta_kubernetes_service_annotation_prometheus_io_scheme]\n      action: replace\n      target_label: __scheme__\n      regex: (https?)\n    - source_labels: [__meta_kubernetes_service_annotation_prometheus_io_path]\n      action: replace\n      target_label: __metrics_path__\n      regex: (.+)\n    - source_labels: [__address__, __meta_kubernetes_service_annotation_prometheus_io_port]\n      action: replace\n      target_label: __address__\n      regex: ([^:]+)(?::\\d+)?;(\\d+)\n      replacement: $1:$2\n    - action: labelmap\n      regex: __meta_kubernetes_service_label_(.+)\n    - source_labels: [__meta_kubernetes_namespace]\n      action: replace\n      target_label: kubernetes_namespace\n    - source_labels: [__meta_kubernetes_service_name]\n      action: replace\n      target_label: kubernetes_name",
        },
    }

    url = f"{base_url}/api/v1/namespaces/{namespace}/configmaps"

    try:
        rsp = wrapper._send_request("{0}/{1}".format(url, config_name))
    except Exception as err:
        rsp = wrapper.requests_post(url, json=data)
    else:
        rsp = wrapper.requests_put("{0}/{1}".format(url, config_name), json=data)

    logger.info(f"Config map response: {rsp.json()}")


def _create_prometheus_service(
    wrapper,
    base_url,
    namespace,
    app_name,
    prometheus_port,
    ec2_instance_public_ips,
    service_name="prometheus-service",
):
    # data = {
    #     "apiVersion": "v1",
    #     "kind": "Service",
    #     "metadata": {
    #         "name": service_name,
    #         "namespace": namespace,
    # "annotations": {
    #     "prometheus.io/scrape": "true",
    #     "prometheus.io/port": "9090",
    # },
    #     },
    #     "spec": {
    #         "selector": {"app": app_name},
    #         "type": "LoadBalancer",
    #         "ports": [{"port": 8086, "targetPort": 9090}],
    #     },
    # }

    data = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": service_name,
            "namespace": namespace,
            "annotations": {
                "prometheus.io/scrape": "true",
                "prometheus.io/port": "9090",
            },
        },
        "spec": {
            "type": "NodePort",
            "ports": [
                {
                    "protocol": "TCP",
                    "port": prometheus_port,
                    "targetPort": 9090,
                    "nodePort": prometheus_port,
                }
            ],
            "selector": {"app": app_name},
            "externalIPs": ec2_instance_public_ips,
        },
    }

    url = f"{base_url}/api/v1/namespaces/{namespace}/services"

    rsp = wrapper.requests_post(url, json=data)

    logger.info(f"Prometheus service response: {rsp.json()}")


def _create_prometheus_deployment(
    wrapper, base_url, namespace, app_name, deployment_name="prometheus-deployment"
):
    data = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": deployment_name,
            "namespace": namespace,
            "labels": {"app": app_name},
        },
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": {"app": app_name}},
            "template": {
                "metadata": {"labels": {"app": app_name}},
                "spec": {
                    "containers": [
                        {
                            "name": "prometheus",
                            "image": "prom/prometheus",
                            "args": [
                                "--storage.tsdb.retention.time=12h",
                                "--config.file=/etc/prometheus/prometheus.yml",
                                "--storage.tsdb.path=/prometheus/",
                            ],
                            "ports": [{"containerPort": 9090}],
                            "resources": {
                                "requests": {"cpu": "500m", "memory": "500M"},
                                "limits": {"cpu": 1, "memory": "1Gi"},
                            },
                            "volumeMounts": [
                                {
                                    "name": "prometheus-config-volume",
                                    "mountPath": "/etc/prometheus/",
                                },
                                {
                                    "name": "prometheus-storage-volume",
                                    "mountPath": "/prometheus/",
                                },
                            ],
                        }
                    ],
                    "volumes": [
                        {
                            "name": "prometheus-config-volume",
                            "configMap": {
                                "defaultMode": 420,
                                "name": "prometheus-server-conf",
                            },
                        },
                        {"name": "prometheus-storage-volume", "emptyDir": {}},
                    ],
                },
            },
        },
    }

    url = f"{base_url}/apis/apps/v1/namespaces/{namespace}/deployments"

    rsp = wrapper.requests_post(url, json=data)

    logger.info(f"Prometheus deployments response: {rsp.json()}")

def get_resource_handler_and_region_name(oc_handler):
    """
    Get AWS Resource Handler and region from the environment
    associated with the Container Orchestrator.
    """

    env = oc_handler.environment_set.filter(resource_handler__resource_technology__slug="aws").first()

    if not env:
        raise ValueError(
            f"No AWS environment associated with Container Orchestrator "
            f"'{oc_handler.name}'"
        )

    if not env.resource_handler:
        raise ValueError(
            f"No Resource Handler associated with environment '{env.name}'"
        )

    region_name = env.aws_region

    if not region_name:
        raise ValueError(
            f"No AWS region configured for environment '{env.name}'"
        )

    rh = env.resource_handler.cast()

    logger.info(
        f"Container Orchestrator: {oc_handler.name}, "
        f"Environment: {env.name}, "
        f"Region: {region_name}"
    )

    return rh, region_name

def get_cluster_node_public_ip(oc_handler, base_url, rh, region_name):
    """
    Get eks cluster node list
    """
    wrapper = oc_handler.get_api_wrapper()

    url = f"{base_url}/api/v1/nodes"

    rsp = wrapper._send_request(url)

    logger.info(f"container node list response: {rsp.json()}")

    ec2_instance_ids = [
        item_obj["spec"]["providerID"].split("/")[-1]
        for item_obj in rsp.json()["items"]
    ]

    if not ec2_instance_ids:
        return [], []

    oc_handler.environment_set.all()
    # get ec2 boto3 client
    client = rh.get_boto3_client(region_name=region_name, service_name="ec2")

    # get  ec2 instance details
    ec2_rsp = client.describe_instances(InstanceIds=ec2_instance_ids)

    public_ips = [
        ec2_inst["PublicIpAddress"]
        for item_obj in ec2_rsp["Reservations"]
        for ec2_inst in item_obj["Instances"]
    ]

    sg_group_ids = [
        xx["GroupId"]
        for item_obj in ec2_rsp["Reservations"]
        for ec2_inst in item_obj["Instances"]
        for xx in ec2_inst["SecurityGroups"]
    ]

    return public_ips, sg_group_ids


def add_security_rule(rh, region_name, sg_group_id, node_port):
    """
    Add eks prometheus port security rule
    """
    ec2_client = rh.get_boto3_resource(region_name=region_name, service_name="ec2")

    security_group = ec2_client.SecurityGroup(sg_group_id)

    # Enable Prometheus port
    security_group.authorize_ingress(
        IpProtocol="tcp", CidrIp="0.0.0.0/0", FromPort=node_port, ToPort=node_port
    )


def verify_or_create_a_new_rule(sg_group_ids, node_port, rh, region_name):
    """
    Verify existing security group rule, if not exist, add new rule
    """
    ec2_client = rh.get_boto3_client(region_name=region_name, service_name="ec2")

    for sg_group_id in sg_group_ids:
        sg_rsp = ec2_client.describe_security_groups(GroupIds=[sg_group_id])

        if not sg_rsp["SecurityGroups"]:
            add_security_rule(rh, region_name, sg_group_id, node_port)

            continue

        is_match = False

        for ipPermissions in sg_rsp["SecurityGroups"]:
            for xx in ipPermissions["IpPermissions"]:
                if (
                    "FromPort" in xx
                    and xx["FromPort"] == node_port
                    and "ToPort" in xx
                    and xx["ToPort"] == node_port
                    and "IpProtocol" in xx
                    and xx["IpProtocol"] == "tcp"
                ):
                    is_match = True
                    break

        if not is_match:
            add_security_rule(rh, region_name, sg_group_id, node_port)


def create_cf_as_per_nips(index_no):
    """
    get or create cf as needed as per number of ips
    """

    CustomField.objects.get_or_create(
        name=f"prometheus_url_{index_no}",
        defaults={
            "label": f"Prometheus URL-{index_no}",
            "type": "URL",
            "description": "Used by the EKS Prometheus Portal",
            "required": True,
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )


def run(job, resource, *args, **kwargs):
    set_progress("Starting Provision of Prometheus portal...")

    # get or create custom fields as needed
    get_or_create_custom_fields()

    oc_handler = Kubernetes.objects.get(id="{{container_orchestrator_id}}")
    prometheus_port = int("{{prometheus_port}}")

    base_url = "{0}://{1}:{2}".format(
        oc_handler.protocol, oc_handler.ip, oc_handler.port
    )

    rh_handler, region_name = get_resource_handler_and_region_name(oc_handler.cast())

    try:
        # get ec2 instance public ip
        ec2_instance_public_ips, sg_group_ids = get_cluster_node_public_ip(
            oc_handler.cast(), base_url, rh_handler, region_name
        )
        # add esk prometheus port security group
        verify_or_create_a_new_rule(
            sg_group_ids, prometheus_port, rh_handler, region_name
        )
    except Exception as err:
        logger.error(err)
        return "FAILURE", f"{err}", ""

    wrapper = oc_handler.cast().get_api_wrapper()

    namespace = "prometheus"
    cluster_role_name = "prometheus-role"
    cluster_role_binding_name = "prometheus-role-binding"
    config_name = "prometheus-server-conf"
    service_name = "prometheus-service"
    deployment_name = "prometheus-deployment"
    app_name = "prometheus-server"

    try:
        _get_or_create_namespaces(wrapper, base_url, namespace)
        _create_cluster_role(wrapper, cluster_role_name)
        _create_cluster_role_binding(
            wrapper, namespace, cluster_role_name, cluster_role_binding_name
        )
        _create_config_map(wrapper, base_url, namespace, config_name)
        _create_prometheus_service(
            wrapper,
            base_url,
            namespace,
            app_name,
            prometheus_port,
            ec2_instance_public_ips,
            service_name,
        )
        _create_prometheus_deployment(
            wrapper, base_url, namespace, app_name, deployment_name
        )
    except Exception as err:
        logger.error(err)
        return "FAILURE", f"{err}", ""

    prometheus_url_dict = {}

    if len(ec2_instance_public_ips) == 1:
        prometheus_url = "http://{0}:{1}".format(
            ec2_instance_public_ips[0], prometheus_port
        )

        prometheus_url_dict["prometheus_url"] = prometheus_url
        resource.prometheus_url = prometheus_url

    else:
        for idx, value in enumerate(ec2_instance_public_ips, start=1):
            # create the endpoint custom fields
            create_cf_as_per_nips(idx)

            prometheus_url = "http://{0}:{1}".format(value, prometheus_port)

            # set endpoint value
            setattr(
                resource,
                f"prometheus_url_{idx}",
                prometheus_url,
            )

            prometheus_url_dict[f"prometheus_url_{idx}"] = prometheus_url

    resource.container_orchestrator_id = oc_handler.id
    resource.prometheus_namespace = namespace
    resource.cluster_role_name = cluster_role_name
    resource.cluster_role_binding_name = cluster_role_binding_name
    resource.config_name = config_name
    resource.service_name = service_name
    resource.deployment_name = deployment_name
    resource.app_name = app_name
    resource.prometheus_port = prometheus_port
    resource.save()

    oc_handler = oc_handler.cast()
    oc_handler.prometheus_url = json.dumps(prometheus_url_dict)
    oc_handler.save()
    
    # waiting 1 minute for prometheus pod and deployment to get spin-up 
    time.sleep(60)
    
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

    return "SUCCESS", "Prometheus portal deployed successfully.", ""