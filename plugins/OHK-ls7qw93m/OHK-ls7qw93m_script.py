import json
import requests
import yaml

from infrastructure.models import Environment, CustomField
from containerorchestrators.kuberneteshandler.models import Kubernetes
from common.methods import set_progress
from utilities.logger import ThreadLogger
from resourcehandlers.aws.models import AWSHandler

logger = ThreadLogger(__name__)


def get_boto_client(env_obj, service_name="sts"):
    """
    Create boto3 client using key and password
    """
    # get aws resource handler object
    rh: AWSHandler = env_obj.resource_handler.cast()

    # get aws client object
    client = rh.get_boto3_client(env_obj.aws_region, service_name)

    return client


def _get_boto_resource_client(env_obj, service_name="ec2"):
    """
    Create boto3 resource client using key and password
    """
    # get aws resource handler object
    rh = env_obj.resource_handler.cast()

    # get aws wrapper object
    wrapper = rh.get_api_wrapper()

    # get aws client object
    client = wrapper.get_boto3_resource(
        rh.serviceaccount, rh.servicepasswd, env_obj.aws_region, service_name
    )

    return client


def _get_or_create_node_group_role(env_obj):
    """
    Find a custom node group role or Create a new node group role
    """
    # get iam boto3 client
    iam_client = get_boto_client(env_obj, "iam")

    # assume_role_policy_document for role
    assume_role_policy_document = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
    )

    role_name = "CustomAmazonEKSNodeRole"

    try:
        # get eks node group role
        return iam_client.get_role(RoleName=role_name)["Role"]["Arn"]
    except Exception as err:
        pass

    try:
        # create eks node group role
        role_rsp = iam_client.create_role(
            Path="/",
            RoleName=role_name,
            AssumeRolePolicyDocument=assume_role_policy_document,
            Description="Allows EC2 instances to call nodegroup on your behalf.",
            MaxSessionDuration=3600,
        )
    except Exception as err:
        iam_client.delete_role(RoleName=role_name)
        raise RuntimeError(f"Role could not be created...{err}")

    for policy in [
        "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
        "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
        "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
    ]:
        try:
            # attach policy to eks node group role
            policy_attach_res = iam_client.attach_role_policy(
                RoleName=role_name, PolicyArn=policy
            )
        except Exception as error:
            raise RuntimeError(f"policy could not be created...{error}")

    return role_rsp["Role"]["Arn"]


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


def _create_cluster_role(
    wrapper, cluster_role_name="eks-console-dashboard-full-access-clusterrole"
):
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
                ],
                "verbs": ["get", "list"],
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
                "verbs": ["get", "list"],
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
    wrapper, cluster_role_bindning_name="eks-console-dashboard-full-access-binding"
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
        "metadata": {"name": cluster_role_bindning_name},
        "subjects": [
            {
                "kind": "Group",
                "name": "eks-console-dashboard-full-access-group",
                "apiGroup": "rbac.authorization.k8s.io",
            }
        ],
        "roleRef": {
            "kind": "ClusterRole",
            "name": "eks-console-dashboard-full-access-clusterrole",
            "apiGroup": "rbac.authorization.k8s.io",
        },
    }

    try:
        rsp = wrapper._send_request("{0}/{1}".format(url, cluster_role_bindning_name))
    except Exception as err:
        rsp = wrapper.requests_post(url, json=data)

    logger.info(f"cluster role binding response: {rsp.json()}")


def _create_port_forward_role(
    wrapper,
    base_url,
    role_name="kube-saas:list-and-logs",
    namespace="nginx-deployment-name",
):
    """
    Create a Kubernetes port forward role
    """

    # get or create namespace for deployment
    _get_or_create_namespaces(wrapper, base_url, namespace)

    data = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "Role",
        "metadata": {"name": role_name, "namespace": namespace},
        "rules": [
            {
                "apiGroups": [""],
                "resources": ["*"],
                "verbs": [
                    "get",
                    "list",
                    "watch",
                    "create",
                    "update",
                    "patch",
                    "delete",
                ],
            }
        ],
    }

    url = f"{base_url}/apis/rbac.authorization.k8s.io/v1/namespaces/{namespace}/roles"

    try:
        rsp = wrapper._send_request("{0}/{1}".format(url, role_name))
    except Exception as err:
        rsp = wrapper.requests_post(url, json=data)

    logger.info(f"Port Forward role response: {rsp.json()}")


def _create_port_forward_role_binding(
    wrapper,
    base_url,
    user_name,
    role_name="kube-saas:list-and-logs",
    role_binding_name="allow-port-forward",
    namespace="nginx-deployment-name",
):
    """
    Create a Kubernetes port forward role bindings
    """
    data = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "RoleBinding",
        "metadata": {"name": role_binding_name, "namespace": namespace},
        "subjects": [
            {"kind": "User", "name": user_name, "apiGroup": "rbac.authorization.k8s.io"}
        ],
        "roleRef": {"kind": "Role", "name": role_name},
    }

    url = f"{base_url}/apis/rbac.authorization.k8s.io/v1/namespaces/{namespace}/rolebindings"

    try:
        rsp = wrapper._send_request("{0}/{1}".format(url, role_binding_name))
    except Exception as err:
        rsp = wrapper.requests_post(url, json=data)

    logger.info(f"Port Forward role bindning response: {rsp.json()}")


def _create_config_map(
    wrapper, env_obj, base_url, namespace="kube-system", confgig_name="aws-auth"
):
    """
    Create a Kubernetes cluster aws auth config
    """
    # get or create namespace for aws auth config
    _get_or_create_namespaces(wrapper, base_url, namespace)

    # get sts client
    sts_client = get_boto_client(env_obj)

    # get resource handler user identity
    sts_identity = sts_client.get_caller_identity()

    # get or create eks node group role
    NODE_GROUP_ROLE = _get_or_create_node_group_role(env_obj)
    SSO_ROLE = sts_identity["Arn"]
    SSO_USERNAME = sts_identity["UserId"]
    # LOGIN_USER_ROLE = 'arn:aws:iam::user_id:role/Federated user role'
    # LOGIN_USERNAME = "abc@example.io"

    EC2PrivateDNSName = "{" + "{EC2PrivateDNSName}" + "}"

    # create role binding
    _create_port_forward_role_binding(wrapper, base_url, sts_identity["UserId"])

    # without Federated user role map
    MAP_ROLE = f"- rolearn: {NODE_GROUP_ROLE}\n  username: system:node:{EC2PrivateDNSName}\n  groups:\n  - system:bootstrappers\n  - system:nodes\n- rolearn:  {SSO_ROLE}\n  username: {SSO_USERNAME}\n  groups:\n  - system:master\n  - eks-console-dashboard-full-access-group\n"

    # with Federated user role map
    # MAP_ROLE = f"""- rolearn: {NODE_GROUP_ROLE}\n  username: system:node:{EC2PrivateDNSName}\n  groups:\n  - system:bootstrappers\n  - system:nodes\n- rolearn: {LOGIN_USER_ROLE}\n  username: {LOGIN_USERNAME}\n  groups:\n  - system:master\n  - eks-console-dashboard-full-access-group\n- rolearn:  {SSO_ROLE}\n  username: {SSO_USERNAME}\n  groups:\n  - system:master\n  - eks-console-dashboard-full-access-group\n"""

    data = {
        "apiVersion": "v1",
        "data": {"mapRoles": MAP_ROLE.replace("\\n", "\n")},
        "metadata": {
            "name": confgig_name,
            "namespace": namespace,
        },
    }

    url = f"{base_url}/api/v1/namespaces/{namespace}/configmaps"

    try:
        rsp = wrapper._send_request("{0}/{1}".format(url, confgig_name))
    except Exception as err:
        rsp = wrapper.requests_post(url, json=data)
    else:
        rsp = wrapper.requests_put("{0}/{1}".format(url, confgig_name), json=data)

    logger.info(f"Config map response: {rsp.json()}")


def _create_nginx_service(
    wrapper,
    base_url,
    ec2_instance_public_ips,
    node_port,
    namespace="nginx-deployment-name",
):
    """
    Create a Nginx service
    """
    # get or create namespace for Nginx service
    _get_or_create_namespaces(wrapper, base_url, namespace)

    data = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": "demo-nginx-service"},
        "spec": {
            "type": "NodePort",
            "ports": [
                {"protocol": "TCP", "port": 80, "targetPort": 80, "nodePort": node_port}
            ],
            "selector": {"app": "demo-nginx"},
            "externalIPs": ec2_instance_public_ips,
        },
    }

    url = f"{base_url}/api/v1/namespaces/{namespace}/services"

    rsp = wrapper.requests_post(url, json=data)

    logger.info(f"Nginx service response: {rsp.json()}")


def _create_nginx_deployment(wrapper, base_url, namespace_name="nginx-deployment-name"):
    """
    Create a Nginx deployment and pods
    """
    # get or create namespace for Nginx deployments
    _get_or_create_namespaces(wrapper, base_url, namespace_name)

    data = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "demo-nginx-test", "labels": {"app": "demo-nginx"}},
        "spec": {
            "selector": {"matchLabels": {"app": "demo-nginx"}},
            "replicas": 1,
            "template": {
                "metadata": {
                    "name": "demo-nginx-test",
                    "labels": {"app": "demo-nginx"},
                },
                "spec": {"containers": [{"name": "nginx-pod", "image": "nginx"}]},
            },
        },
    }

    url = f"{base_url}/apis/apps/v1/namespaces/{namespace_name}/deployments"

    rsp = wrapper.requests_post(url, json=data)

    logger.info(f"Nginx deployments response: {rsp.json()}")



def _get_cluster_node_public_ip(wrapper, env_obj, base_url):
    """
    Get eks cluster node list and resolve IPs dynamically (Public or Private fallback)
    """
    url = f"{base_url}/api/v1/nodes"
    rsp = wrapper._send_request(url)

    logger.info(f"Grafana node list response: {rsp.json()}")

    ec2_instance_ids = [
        item_obj["spec"]["providerID"].split("/")[-1]
        for item_obj in rsp.json()["items"]
    ]

    if not ec2_instance_ids:
        return [], []

    client = get_boto_client(env_obj, service_name="ec2")

    ec2_rsp = client.describe_instances(InstanceIds=ec2_instance_ids)

    resolved_ips = []
    for item_obj in ec2_rsp["Reservations"]:
        for ec2_inst in item_obj["Instances"]:
            ip = ec2_inst.get("PublicIpAddress") or ec2_inst.get("PrivateIpAddress")
            if ip:
                resolved_ips.append(ip)

    sg_group_ids = [
        xx["GroupId"]
        for item_obj in ec2_rsp["Reservations"]
        for ec2_inst in item_obj["Instances"]
        for xx in ec2_inst["SecurityGroups"]
    ]

    return resolved_ips, sg_group_ids


def _add_security_rule(sg_group_id, node_port, env_obj):
    """
    Add eks port security rule
    """
    ec2_client = _get_boto_resource_client(env_obj, service_name="ec2")

    security_group = ec2_client.SecurityGroup(sg_group_id)

    # Enable eks port
    security_group.authorize_ingress(
        IpProtocol="tcp", CidrIp="0.0.0.0/0", FromPort=node_port, ToPort=node_port
    )


def _verify_or_create_a_new_rule(sg_group_ids, node_port, env_obj):
    """
    Verify existing security group rule, if not exist, add new rule
    """
    ec2_client = get_boto_client(env_obj, service_name="ec2")

    for sg_group_id in sg_group_ids:
        sg_rsp = ec2_client.describe_security_groups(GroupIds=[sg_group_id])

        if not sg_rsp["SecurityGroups"]:
            _add_security_rule(sg_group_id, node_port, env_obj)

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
            _add_security_rule(sg_group_id, node_port, env_obj)


def create_cf_as_per_nips(index_no):
    """
    get or create cf as needed as per number of ips
    """

    CustomField.objects.get_or_create(
        name=f"nginx_server_endpoint_{index_no}",
        defaults={
            "label": f"Nginx Endpoint-{index_no}",
            "type": "URL",
            "description": "Used by the AWS EKS blueprint",
            "required": True,
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )


def run(job, *args, **kwargs):
    set_progress("Starting Provision of Nginx deployments...")

    # get resource object
    resource = job.resource_set.first()

    # get kubernetes model object
    kub_obj = Kubernetes.objects.get(id=resource.container_orchestrator_id)

    # environment model object
    env_obj = Environment.objects.get(id=resource.env_id)

    wrapper = kub_obj.get_api_wrapper()

    base_url = "{0}:443".format(resource.endpoint)
    node_port = 30092

    try:
        # get ec2 instance public ip
        ec2_instance_public_ips, sg_group_ids = _get_cluster_node_public_ip(
            wrapper, env_obj, base_url
        )

        # add esk port security group
        _verify_or_create_a_new_rule(sg_group_ids, node_port, env_obj)

        # create cluster role
        _create_cluster_role(wrapper)

        # create cluster role binding
        _create_cluster_role_binding(wrapper)

        # create port forward role
        _create_port_forward_role(wrapper, base_url)

        # create eks config map
        _create_config_map(wrapper, env_obj, base_url)

        # create nginx service
        _create_nginx_service(wrapper, base_url, ec2_instance_public_ips, node_port)

        # deploy nginx server
        _create_nginx_deployment(wrapper, base_url)

    except Exception as err:
        logger.error(err)

        return "FAILURE", f"{err}", ""

    if len(ec2_instance_public_ips) == 1:
        resource.nginx_server_endpoint = "http://{0}:{1}".format(
            ec2_instance_public_ips[0], node_port
        )

    else:
        for idx, value in enumerate(ec2_instance_public_ips, start=1):
            # create the endpoint custom fields
            create_cf_as_per_nips(idx)

            # set endpoint value
            setattr(
                resource,
                f"nginx_server_endpoint_{idx}",
                "http://{0}:{1}".format(value, node_port),
            )

    resource.save()


    try:
        # sync namespaces
        kub_obj.sync_resource_metadata(sync_resource_type="sync_namespaces")
        # sync deployments
        kub_obj.sync_resource_metadata(sync_resource_type="sync_deployments")
        # sync nodes
        kub_obj.sync_resource_metadata(sync_resource_type="sync_nodes")
        # sync pods
        kub_obj.sync_resource_metadata(sync_resource_type="sync_pods")
    except Exception as err:
        pass

    return "SUCCESS", "Nginx server deployed successfully.", ""