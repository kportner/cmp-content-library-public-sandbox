"""
Build service item action for AWS EKS Cluster Service blueprint.
"""
from __future__ import unicode_literals
import json
import random
import string
import time
from botocore.exceptions import ClientError
from accounts.models import Group

from common.methods import set_progress
from infrastructure.models import CustomField, Environment, Namespace
from containerorchestrators.kuberneteshandler.models import Kubernetes
from containerorchestrators.models import ContainerOrchestratorTechnology
from resourcehandlers.aws.models import AWSHandler
from resources.models import ResourceType, Resource
from utilities.logger import ThreadLogger
from django.core.files.uploadedfile import SimpleUploadedFile
from cbhooks.models import CloudBoltHook

logger = ThreadLogger(__name__)


def create_required_parameters():
    """
    We create the containerorchestrator namespace, to keep this CF from adding noise to
    the Parameters list page.
    """
    namespace, _ = Namespace.objects.get_or_create(name="containerorchestrators")
    CustomField.objects.get_or_create(
        name="container_orchestrator_id",
        defaults=dict(
            label="Container Orchestrator ID",
            description=(
                "Used by the Multi-Node Kubernetes Blueprint. Maps the provisioned CloudBolt resource"
                "to the Container Orchestrator used to manage the Kubernetes cluster."
            ),
            type="INT",
            namespace=namespace,
        ),
    )

    CustomField.objects.get_or_create(
        name="create_eks_k8s_cluster_name",
        defaults=dict(
            label="EKS Cluster: Cluster Name",
            description="Used by the EKS blueprint",
            type="STR",
            namespace=namespace,
        ),
    )
        
    CustomField.objects.get_or_create(
        name="subnet_type",
        defaults={
            "label": "Eks Subnet Type",
            "description": "Filter subnets by Public or Private tier.",
            "type": "STR",
        },
    )


def get_or_create_custom_fields():
    """
    Helper functions for main function to create custom field as needed
    """
    CustomField.objects.get_or_create(
        name="aws_rh_id",
        defaults={
            "label": "RH ID",
            "type": "STR",
        },
    )
    CustomField.objects.get_or_create(
        name="aws_region",
        defaults={
            "label": "Region ID",
            "type": "STR",
        },
    )
    CustomField.objects.get_or_create(
        name="vpc_id",
        defaults={
            "label": "VPC ID",
            "type": "STR",
        },
    )

    CustomField.objects.get_or_create(
        name="env_id",
        defaults={
            "label": "ENV ID",
            "type": "STR",
        },
    )
    CustomField.objects.get_or_create(
        name="eks_cluster_name",
        type="STR",
        defaults={
            "label": "Cluster Name",
            "description": "Used by the AWS EKS blueprint.",
        },
    )
    CustomField.objects.get_or_create(
        name="arn",
        type="STR",
        defaults={
            "label": "ARN",
            "description": "Used by the AWS EKS blueprint.",
            "show_as_attribute": True,
        },
    )
    CustomField.objects.get_or_create(
        name="created_at",
        type="STR",
        defaults={
            "label": "Create At",
            "description": "Used by the AWS EKS blueprint.",
        },
    )
    CustomField.objects.get_or_create(
        name="kubernetes_version",
        type="STR",
        defaults={
            "label": "Kubernetes Version",
            "description": "Used by the AWS EKS blueprint.",
            "show_as_attribute": True,
        },
    )
    CustomField.objects.get_or_create(
        name="status",
        type="STR",
        defaults={
            "label": "Status",
            "description": "Used by the AWS EKS blueprint.",
            "show_as_attribute": True,
        },
    )
    CustomField.objects.get_or_create(
        name="role_arn",
        type="STR",
        defaults={
            "label": "Cluster Role ARN",
            "description": "Used by the AWS EKS blueprint.",
            "show_as_attribute": True,
        },
    )
    CustomField.objects.get_or_create(
        name="platform_version",
        type="STR",
        defaults={
            "label": "Cluster Platform Version",
            "description": "Used by the AWS EKS blueprint.",
        },
    )
    CustomField.objects.get_or_create(
        name="eks_subnets",
        type="STR",
        defaults={"label": "Subnets", "description": "Used by the AWS EKS blueprint."},
    )
    CustomField.objects.get_or_create(
        name="eks_security_groups",
        type="STR",
        defaults={
            "label": "Cluster Security Groups",
            "description": "Used by the AWS EKS blueprint.",
            "show_as_attribute": True,
        },
    )
    CustomField.objects.get_or_create(
        name="eks_nodegroup_name",
        type="STR",
        defaults={
            "label": "AWS EKS Cluster Node Group Name",
            "description": "Used by the AWS EKS blueprint",
        },
    )

    CustomField.objects.get_or_create(
        name="eks_nodegroup_resource_status",
        defaults={
            "label": "Status",
            "type": "STR",
            "description": "Used by the AWS EKS blueprint",
            "required": True,
            "show_as_attribute": True,
        },
    )

    CustomField.objects.get_or_create(
        name="eks_nodegroup_arn",
        defaults={
            "label": "Node Group Arn",
            "type": "STR",
            "description": "Used by the AWS EKS blueprint",
            "required": True,
            "show_as_attribute": True,
        },
    )
    CustomField.objects.get_or_create(
        name="eks_nodegroup_ami_type",
        defaults={
            "label": "AMI Type",
            "type": "STR",
            "description": "Used by the AWS EKS blueprint",
            "required": True,
            "show_as_attribute": True,
        },
    )
    CustomField.objects.get_or_create(
        name="eks_nodegroup_instance_types",
        defaults={
            "label": "Instance Types",
            "type": "STR",
            "description": "Used by the AWS EKS blueprint",
            "required": True,
            "show_as_attribute": True,
        },
    )
    CustomField.objects.get_or_create(
        name="eks_nodegroup_noderole_arn",
        defaults={
            "label": "Role Arn",
            "type": "STR",
            "description": "Used by the AWS EKS blueprint",
            "required": True,
            "show_as_attribute": True,
        },
    )
    CustomField.objects.get_or_create(
        name="eks_nodegroup_node_min_size",
        defaults={
            "label": "Min Size",
            "type": "STR",
            "description": "Used by the AWS EKS blueprint",
            "required": True,
            "show_as_attribute": True,
        },
    )

    CustomField.objects.get_or_create(
        name="eks_nodegroup_node_max_size",
        defaults={
            "label": "Max Size",
            "type": "STR",
            "description": "Used by the AWS EKS blueprint",
            "required": True,
            "show_as_attribute": True,
        },
    )
    CustomField.objects.get_or_create(
        name="eks_nodegroup_desired_size",
        defaults={
            "label": "Desired Size",
            "type": "STR",
            "description": "Used by the AWS EKS blueprint",
            "required": True,
            "show_as_attribute": True,
        },
    )

    CustomField.objects.get_or_create(
        name="grafana_server_endpoint",
        defaults={
            "label": "Grafana Endpoint",
            "type": "URL",
            "description": "Used by the AWS EKS blueprint",
            "required": True,
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )

    CustomField.objects.get_or_create(
        name="endpoint",
        type="URL",
        defaults={
            "label": "Cluster Endpoint",
            "description": "Used by the AWS EKS blueprint.",
            "required": False,
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )


def get_or_create_resource_type():
    """
    get or create resource type
    """
    try:
        rt = ResourceType.objects.get(name="eks_nodegroup")
    except Exception as err:
        rt = ResourceType.objects.create(
            **{
                "name": "eks_nodegroup",
                "label": "EKS Node Group",
                "icon": "far fa-file",
            }
        )

    return rt


def get_boto_client(env_id=None, boto_service="ec2"):
    """
    get_boto_client
    """
    if env_id is None:
        return None

    env = Environment.objects.get(id=env_id)
    rh: AWSHandler = env.resource_handler.cast()

    client = rh.get_boto3_client(env.aws_region, boto_service)
    return client, env


def create_cluster_role(cluster_name, iam_client):
    """
    create_cluster_role
    """
    assume_role_policy_document = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "eks.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
    )

    random_string_role = "".join(
        random.choices(
            string.ascii_uppercase + string.ascii_lowercase + string.digits, k=6
        )
    )
    role_name = cluster_name + "-" + random_string_role + "-Role"

    try:
        cluster_role_rsp = iam_client.create_role(
            Path="/",
            RoleName=role_name,
            AssumeRolePolicyDocument=assume_role_policy_document,
            Description="Allows EKS cluster creation on your behalf.",
            MaxSessionDuration=3600,
        )
    except Exception as err:
        raise RuntimeError(f"Role could not be created...{err}")

    try:
        for policy in ["arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"]:
            iam_client.attach_role_policy(RoleName=role_name, PolicyArn=policy)
    except Exception as error:
        raise RuntimeError(f"policy could not be created...{error}")

    return cluster_role_rsp["Role"]["Arn"]


def generate_options_for_env_id(**kwargs):
    """
    Generate AWS region options
    """
    group_name = kwargs["group"]

    try:
        group = Group.objects.get(name=group_name)
    except Exception as err:
        return []

    # fetch all group environment
    envs = group.get_available_environments()

    aws_envs = [
        env
        for env in envs
        if env.resource_handler is not None
        and env.resource_handler.resource_technology.slug.startswith("aws")
    ]

    if not aws_envs:
        return [("", "Select Valid Group Associated with Environment")]

    options = [("", "Select Environment")]

    for env in aws_envs:
        options.append((env.id, env.name))

    return options


def generate_options_for_k8s_version(**kwargs):
    """
    generate options for kubernetes version
    """
    return ["1.36", "1.35", "1.34", "1.33", "1.32", "1.31", "1.30"]


def generate_options_for_security_groups(control_value=None, server=None, **kwargs):
    """
    generate_options_for_security_groups
    """
    if control_value is None or control_value == "":
        return []

    client, env = get_boto_client(control_value, "ec2")

    response = client.describe_security_groups(
        Filters=[{"Name": "vpc-id", "Values": [env.vpc_id]}]
    )

    return [(scy["GroupId"], scy["GroupName"]) for scy in response["SecurityGroups"]]


def generate_options_for_subnet_type(control_value=None, **kwargs):
    if not control_value:
        return []
    return [
        (f"private@{control_value}", "Private Subnets"),
        (f"public@{control_value}", "Public Subnets")
    ]


def generate_options_for_subnet_1(control_value=None, server=None, **kwargs):
    if not control_value or "@" not in str(control_value):
        return []
    
    chosen_type, env_id = control_value.split("@")
    env = Environment.objects.get(id=env_id)
    rh = env.resource_handler.cast()
    
    target_public = True if chosen_type == "public" else False
    
    return [
        (
            "{0}@{1}@{2}".format(
                subnet["network"], env.id, subnet["availability_zone"]
            ),
            "{0} | {1} | Is Public: {2}".format(
                subnet["name"],
                subnet["availability_zone"],
                subnet["map_public_ip_on_launch"],
            ),
        )
        for subnet in rh.get_all_vpc_subnets(env.aws_region, env.vpc_id)
        if subnet["map_public_ip_on_launch"] == target_public
    ]


def generate_options_for_subnet_2(control_value=None, server=None, **kwargs):
    if not control_value or "@" not in str(control_value):
        return []
        
    try:
        subnet_1, env_id, subnet_1_zone = control_value.split("@")
    except ValueError:
        return []

    env = Environment.objects.get(id=env_id)
    rh = env.resource_handler.cast()
    
    all_subnets = rh.get_all_vpc_subnets(env.aws_region, env.vpc_id)
    subnet_1_meta = next((s for s in all_subnets if s["network"] == subnet_1), None)
    if not subnet_1_meta:
        return []
        
    target_public = subnet_1_meta["map_public_ip_on_launch"]
   
    return [
        (
            f"{subnet['network']}@{env.id}@{subnet_1_zone}@{subnet['availability_zone']}",
            "{0} | {1} | Is Public: {2}".format(
                subnet["name"],
                subnet["availability_zone"],
                subnet["map_public_ip_on_launch"],
            ),
        )
        for subnet in all_subnets
        if subnet["network"] != subnet_1
        and subnet["availability_zone"] != subnet_1_zone
        and subnet["map_public_ip_on_launch"] == target_public
    ]


def generate_options_for_ami_type(control_value=None, **kwargs):
    if not control_value or control_value == "0" or "@" not in str(control_value):
        return []
        
    try:
        parts = str(control_value).split("@")
        if len(parts) >= 4:
            _, env_id, subnet_1_zone, subnet_2_zone = parts
        elif len(parts) == 3:
            env_id, _, subnet_2_zone = parts
            subnet_1_zone = subnet_2_zone
        else:
            return []
    except Exception:
        return []
    
    return [
        ("", "-------Select AMI Type-------"),
        (
            f"x86_64/AL2023_x86_64_STANDARD/{env_id}/{subnet_1_zone}/{subnet_2_zone}",
            "Amazon Linux 2023 (AL2023_x86_64_STANDARD)",
        ),
        (
            f"arm64/AL2023_ARM_64_STANDARD/{env_id}/{subnet_1_zone}/{subnet_2_zone}",
            "Amazon Linux 2023 Arm (AL2023_ARM_64_STANDARD)",
        ),
    ]


def generate_options_for_instance_type(control_value=None, **kwargs):
    options = []

    if not control_value or control_value == "0" or "/" not in str(control_value):
        return options
        
    control_str = str(control_value)
    if control_str.startswith("subnet-") or "@" in control_str:
        return options
        
    try:
        control_parts = control_str.split("/")
        if len(control_parts) < 5:
            return options
            
        architecture = control_parts[0]
        env_id = control_parts[2]
        az_1 = control_parts[3]
        az_2 = control_parts[4]
        
        client, _ = get_boto_client(env_id, "ec2")
        
        ins_off_rsp = client.describe_instance_type_offerings(
            LocationType="availability-zone", 
            Filters=[{"Name": "location", "Values": [az_1, az_2]}]
        )["InstanceTypeOfferings"]

        instance_type_offerings = {}
        for xx in ins_off_rsp:
            instance_type_offerings.setdefault(xx["Location"], []).append(xx["InstanceType"])
        
        if not instance_type_offerings or az_1 not in instance_type_offerings or az_2 not in instance_type_offerings:
            return []
        
        for instance_type in client.describe_instance_types()["InstanceTypes"]:
            if instance_type["ProcessorInfo"]["SupportedArchitectures"][0] == architecture:
                ins_type = instance_type["InstanceType"]
                
                if ins_type not in instance_type_offerings[az_1] or ins_type not in instance_type_offerings[az_2]:
                    continue
                
                vcpu = instance_type["VCpuInfo"]["DefaultVCpus"]
                memory = instance_type["MemoryInfo"]["SizeInMiB"]
                
                options.append(
                    (
                        ins_type,
                        ins_type
                        + "("
                        + "vCPU: Up to   "
                        + str(vcpu)
                        + " "
                        + "vCPUs"
                        + "   "
                        + "memory: "
                        + str(memory / 1024)
                        + " GiB"
                        + ")",
                    )
                )
        
        return sorted(options, key=lambda tup: tup[1].lower())
    except Exception as err:
        logger.error(f"Error executing generate_options_for_instance_type: {err}")
        return []


def _get_or_create_node_group_role(env_obj):
    """
    Find a custom node group role or Create a new node group role
    """
    # get iam boto3 client
    iam_client, _ = get_boto_client(env_obj.id, "iam")

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
            iam_client.attach_role_policy(RoleName=role_name, PolicyArn=policy)
        except Exception as error:
            raise RuntimeError(f"policy could not be created...{error}")

    return role_rsp["Role"]["Arn"]


def create_eks_nodegroup(
    client,
    resource,
    nodegroup_name,
    nodegroup_role,
    ami_type,
    desired_size,
    min_size,
    max_size,
):
    """
    create_eks_nodegroup
    """
    # subnet from cluster resource
    subnets = [sub.strip(" '[]") for sub in resource.eks_subnets.split(",")]

    try:
        nodegroup_rsp = client.create_nodegroup(
            clusterName=resource.name,
            nodegroupName=nodegroup_name,
            scalingConfig={
                "minSize": min_size,
                "maxSize": max_size,
                "desiredSize": desired_size,
            },
            diskSize=int("{{disk_size}}"),
            subnets=subnets,
            instanceTypes=["{{instance_type}}"],
            amiType=ami_type,
            nodeRole=nodegroup_role,
        )["nodegroup"]

    except ClientError as err:
        set_progress("AWS ClientError: {}".format(err))
        raise RuntimeError(f"EKS NodeGroup creation failed - {err}")

    except Exception as err:
        raise RuntimeError(f"EKS NodeGroup creation failed - {err}")

    while nodegroup_rsp["status"] == "CREATING":
        set_progress(
            "Node Group \"{}\" is being created".format(nodegroup_rsp["nodegroupName"]),
            increment_tasks=1,
        )
        time.sleep(60)

        nodegroup_rsp = client.describe_nodegroup(
            clusterName=resource.name, nodegroupName=nodegroup_rsp["nodegroupName"]
        )["nodegroup"]

    if nodegroup_rsp["status"] == "ACTIVE":
        logger.info(f"Node Group response: {nodegroup_rsp}")
        return nodegroup_rsp
    else:
        raise RuntimeError(f"EKS NodeGroup creation failed - {nodegroup_rsp['status']}")


def create_eks_nodegroup_cb_subresource(resource, resource_type, create_ng_obj):
    """
    Create nodegroup cb sub resource
    params: resource : resource object
    params: resource : resource_type object
    params: create_ng_obj : eks nodegroup object
    """

    # create nodegroup as a sub resource of blueprint
    res = Resource.objects.create(
        group=resource.group,
        parent_resource=resource,
        resource_type=resource_type,
        name=create_ng_obj["nodegroupName"],
        blueprint=resource.blueprint,
        lifecycle="ACTIVE",
        owner=resource.owner,
    )

    res.eks_nodegroup_resource_status = create_ng_obj["status"]
    res.eks_nodegroup_arn = create_ng_obj["nodegroupArn"]
    res.eks_nodegroup_ami_type = create_ng_obj["amiType"]
    res.eks_nodegroup_instance_types = create_ng_obj["instanceTypes"]
    res.eks_nodegroup_noderole_arn = create_ng_obj["nodeRole"]
    res.eks_nodegroup_node_min_size = create_ng_obj["scalingConfig"]["minSize"]
    res.eks_nodegroup_node_max_size = create_ng_obj["scalingConfig"]["maxSize"]
    res.eks_nodegroup_desired_size = create_ng_obj["scalingConfig"]["desiredSize"]
    res.save()

    logger.info(f"Sub Resource {res} created successfully.")


def boto_instance_to_dict(cluster, env_id):
    """
    Create a pared-down representation of an eks instance from the full boto
    dictionary.
    """
    instance = {
        "eks_cluster_name": cluster["name"],
        "arn": cluster["arn"],
        "created_at": cluster["createdAt"],
        "kubernetes_version": cluster["version"],
        "role_arn": cluster["roleArn"],
        "platform_version": cluster["platformVersion"],
        "eks_security_groups": cluster["resourcesVpcConfig"]["securityGroupIds"],
        "eks_subnets": cluster["resourcesVpcConfig"]["subnetIds"],
        "vpc_id": cluster["resourcesVpcConfig"]["vpcId"],
        "env_id": env_id,
        "endpoint": cluster["endpoint"],
        "status": cluster["status"],
    }

    logger.info(f"eks instance created: {instance}")
    return instance


CLOUDBOLT_HOOK_TEMPLATE = """
def should_display(resource, request=None):
    if resource.resource_type.name == "cluster":
        return True
    else:
        return False
"""


def add_cloudbolt_condition_hook(job):
    """
    This function creates and adds the condition to all the resource actions for this blueprint
    """
    name = "Should Display Resource Action only If resource is Cluster?"
    plugin, created = CloudBoltHook.objects.get_or_create(name=name)
    plugin.shared = True
    plugin.module_file = SimpleUploadedFile(
        f"cb_plugin_{plugin.id}.py", CLOUDBOLT_HOOK_TEMPLATE.encode("utf8")
    )
    plugin.save()
    job.set_progress("CloudBoltHook Created Successfully")
    return plugin


def run(job, resource, logger=None, **kwargs):
    set_progress("Starting Provision of EKS Cluster...")

    # get or create custom fields as needed
    get_or_create_custom_fields()

    # create required parameter for container orchestrator
    create_required_parameters()

    # get or create resource type and custom fields
    resource_type = get_or_create_resource_type()

    security_groups = "{{security_groups}}"
    cluster_name = "{{ cluster_name }}"
    env_id = "{{ env_id }}"

    # Network Configuration
    chosen_subnet_type = "{{ subnet_type }}"
    subnets = ["{{ subnet_1 }}", "{{ subnet_2 }}"]
    subnets = [i.split("@")[0] for i in subnets]

    nodegroup_name = "{{ nodegroup_name }}"
    ami_type = "{{ami_type}}".split("/")[1]

    desired_size = int("{{desired_nodes}}")
    min_size = int("{{min_nodes}}")
    max_size = int("{{max_nodes}}")

    if max_size < desired_size:
        raise RuntimeError(
            f"Desired nodes {desired_size} should be equal or less than Max node {max_size}".format(
                desired_size, max_size
            )
        )
    elif min_size > desired_size:
        raise RuntimeError(
            f"Min nodes {min_size} should not be greater than desired nodes {desired_size}".format(
                min_size, desired_size
            )
        )

    # eks client
    client, environment = get_boto_client(env_id, "eks")

    # iam client
    iam_client, _ = get_boto_client(env_id, "iam")

    # cluster role arn
    role_arn = create_cluster_role(cluster_name, iam_client)

    # resource handler
    rh = environment.resource_handler.cast()

    resource.name = cluster_name
    resource.cluster_name = cluster_name
    resource.aws_region = environment.aws_region

    # Store the resource handler's ID on this resource so the teardown action
    # knows which credentials to use.
    resource.aws_rh_id = rh.id

    # Cluster creation typically takes between 10 and 15 minutes.
    try:
        cluster_rsp = client.create_cluster(
            name=cluster_name,
            version="{{ k8s_version }}",
            roleArn=role_arn,
            resourcesVpcConfig={
                "subnetIds": subnets,
                "endpointPublicAccess": True,
                "endpointPrivateAccess": True,
                "securityGroupIds": [security_groups]
            },
        )["cluster"]
    except ClientError as e:
        set_progress("AWS ClientError: {}".format(e))
        return "FAILURE", "", e
    except Exception as err:
        return "FAILURE", "Amazon EKS cluster could not be created", str(err)

    while cluster_rsp["status"] == "CREATING":
        set_progress(
            "Cluster \"{}\" is being created".format(cluster_name), increment_tasks=1
        )
        time.sleep(60)

        cluster_rsp = client.describe_cluster(name=cluster_name)["cluster"]

    logger.info(f"Cluster response: {cluster_rsp}")

    # creation of container orchestrator object
    tech = ContainerOrchestratorTechnology.objects.get(name="Kubernetes")
    if hasattr(Kubernetes, "resource_handler"):
        kubernetes = Kubernetes.objects.create(
            name=cluster_name,
            ip=cluster_rsp["endpoint"].strip("https://"),
            port=443,
            protocol="https",
            auth_type="TOKEN",
            serviceaccount=rh.serviceaccount,
            servicepasswd="",
            container_technology=tech,
            resource_handler=rh,
            auto_rotate_token=True,
        )
    else:
        kubernetes = Kubernetes.objects.create(
            name=cluster_name,
            ip=cluster_rsp["endpoint"].strip("https://"),
            port=443,
            protocol="https",
            auth_type="TOKEN",
            serviceaccount=rh.serviceaccount,
            servicepasswd="",
            container_technology=tech
        )
    
    kubernetes.environment_set.add(environment)
    resource.container_orchestrator_id = kubernetes.id

    eks_instance = boto_instance_to_dict(cluster_rsp, env_id)

    for key, value in eks_instance.items():
        setattr(resource, key, value)  # set custom field value

    resource.save()

    # create a new Environment for the new container orchestrator, and attach it to eks cluster
    Environment.objects.create(
        name="Resource-{} Environment#{}".format(resource.name, environment.aws_region),
        container_orchestrator=kubernetes,
    )

    job.set_progress("EkS cluster created successfully")
    job.set_progress("Starting Provision of EKS Cluster Node Group...")

    # create unique role for nodegroup
    nodegroup_role = _get_or_create_node_group_role(environment)

    # create nodegroup
    create_ng_obj = create_eks_nodegroup(
        client,
        resource,
        nodegroup_name,
        nodegroup_role,
        ami_type,
        desired_size,
        min_size,
        max_size,
    )

    # create eks nodegroup cb sub resource
    create_eks_nodegroup_cb_subresource(resource, resource_type, create_ng_obj)
    job.set_progress("EkS cluster node group created successfully")

    # Get Blueprint 
    blueprint = resource.blueprint
    
    # Get All Resource Actions from Blueprint
    resource_actions = blueprint.resourceaction_set.all()
    
    job.set_progress("Create The CloudBoltHook to add condition for the Resource Actions")
    cloudbolt_hook = add_cloudbolt_condition_hook(job)
    
    # Add CloudBoltHook to all Resource Actions
    for resource_action in resource_actions:
        resource_action.condition = cloudbolt_hook
        resource_action.save()

    return "SUCCESS", "EKS Cluster configured successfully", ""