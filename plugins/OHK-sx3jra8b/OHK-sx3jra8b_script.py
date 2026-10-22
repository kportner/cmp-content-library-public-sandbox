from accounts.models import Group
from common.methods import set_progress
from infrastructure.models import Environment
from infrastructure.models import CustomField
from resourcehandlers.aws.models import AWSHandler
from utilities.logger import ThreadLogger
logger = ThreadLogger(__name__)
 

def create_custom_fields_as_needed():
    CustomField.objects.get_or_create(
        name='aws_rh_id', defaults={ 'label': 'AWS RH ID', 'type': 'STR',
            'description': 'Used by the AWS blueprints'
        }
    )
    CustomField.objects.get_or_create(
        name='env_id', defaults={'label': 'Env ID', 'type': 'STR'}
    )
    CustomField.objects.get_or_create(
        name='name', defaults={'label': 'AWS Redshift', 'type': 'STR',
            'description': 'Name of the AWS Redshift cluster'
        }
    )
    CustomField.objects.get_or_create(
        name='cluster_name', defaults={'label': 'AWS Redshift cluster_name', 'type': 'STR',
            'description': 'Name of the AWS Redshift cluster'
        }
    )
    CustomField.objects.get_or_create(
        name='node_type', defaults={'label': 'Redshift cluster Node Type', 'type': 'STR',
            'description': 'The node type to be provisioned for the cluster'
        }
    )
    CustomField.objects.get_or_create(
        name='master_username', defaults={'label': 'Redshift cluster Master Username', 'type': 'STR',
            'description': 'The user name associated with the master user account for the cluster that is being created.'
        }
    )
    CustomField.objects.get_or_create(
        name='master_password', defaults={'label': 'Redshift cluster MasterUserPassword', 'type': 'PWD',
            'description': 'The password associated with the master user account for the cluster that is being created.'
        }
    )
    CustomField.objects.get_or_create(
        name='cluster_type', defaults={'label': 'Redshift cluster Type', 'type': 'STR',
            'description': 'The type of the cluster.'
        }
    )
    CustomField.objects.get_or_create(
        name="vpc_id",
        defaults={
            "label": "VPC",
            "type": "STR",
            "description": "AWS VPC"
        }
    )
    CustomField.objects.get_or_create(
        name="subnet_group",
        defaults={
            "label": "Redshift Cluster Subnet Group",
            "type": "STR",
            "description": "Existing Redshift Cluster Subnet Group"
        }
    )


def connect_to_redshift(env):
    """
    Return boto connection to the redshift in the specified environment's region.
    """
    rh: AWSHandler = env.resource_handler.cast()

    # get aws client object
    client = rh.get_boto3_client(env.aws_region, 'redshift')

    return client, rh.id

def generate_options_for_env_id(server=None, **kwargs):
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
    
    aws_envs= [(env.id, env.name) for env in envs if env.resource_handler is not None and env.resource_handler.resource_technology.slug.startswith('aws')]
    
    return aws_envs

def generate_options_for_cluster_type(**kwargs):
    return [('single-node', 'Single Node'), ('multi-node', 'Multi Node')]
    
def generate_options_for_node_type(field, control_value=None, control_value_dict=None, **kwargs):
    options = []

    if control_value_dict:
        env_id = control_value_dict.get("env_id")
        cluster_type = control_value_dict.get("cluster_type")

        logger.info(f"Environment ID: {env_id}")
        logger.info(f"Cluster Type: {cluster_type}")

        if env_id and cluster_type:
            try:
                env = Environment.objects.get(id=env_id)
                client, _ = connect_to_redshift(env)

                logger.info(f"Environment: {env}")

                paginator = client.get_paginator("describe_orderable_cluster_options")
                node_types = set()

                for page in paginator.paginate():
                    node_types.update(
                        option["NodeType"]
                        for option in page.get("OrderableClusterOptions", [])
                        if option["ClusterType"] == cluster_type
                    )

                options = [(node_type, node_type) for node_type in sorted(node_types)]

                logger.info(f"Supported Node Types: {options}")

            except Exception:
                logger.exception("Failed to fetch Redshift node types.")

    return {
        "options": options,
        "override": True,
        "sort": True,
    }

def generate_options_for_vpc_id(control_value=None, control_value_dict=None,**kwargs):

    options = []

    if not control_value_dict:
        return {"options": options, "override": True}

    env_id = control_value_dict.get("env_id")

    if not env_id:
        return {"options": options, "override": True}

    try:
        env = Environment.objects.get(id=env_id)

        rh = env.resource_handler.cast()
        ec2 = rh.get_boto3_client(env.aws_region, "ec2")

        response = ec2.describe_vpcs()

        options = [
            (
                vpc["VpcId"],
                "{} ({})".format(
                    vpc["VpcId"],
                    vpc.get("Tags", [{}])[0].get("Value", "No Name")
                ),
            )
            for vpc in response.get("Vpcs", [])
        ]

    except Exception:
        logger.exception("Unable to fetch VPCs")

    return {
        "options": options,
        "override": True,
        "sort": True,
    }
    
def generate_options_for_subnet_group(control_value=None,control_value_dict=None,**kwargs):

    options = []

    if not control_value_dict:
        return {
            "options": options,
            "override": True,
        }

    env_id = control_value_dict.get("env_id")
    selected_vpc = control_value_dict.get("vpc_id")

    if not env_id or not selected_vpc:
        return {
            "options": options,
            "override": True,
        }

    try:
        env = Environment.objects.get(id=env_id)
        client, _ = connect_to_redshift(env)

        paginator = client.get_paginator(
            "describe_cluster_subnet_groups"
        )

        for page in paginator.paginate():

            for subnet_group in page.get("ClusterSubnetGroups", []):

                if subnet_group.get("VpcId") == selected_vpc:

                    options.append(
                        (
                            subnet_group["ClusterSubnetGroupName"],
                            subnet_group["ClusterSubnetGroupName"],
                        )
                    )

        if not options:
            options.append(
                (
                    "__NO_SUBNET_GROUP__",
                    "No Redshift Cluster Subnet Groups found for this VPC. Please create one in AWS."
                )
            )

    except Exception:
        logger.exception("Unable to fetch subnet groups")

    return {
        "options": options,
        "override": True,
        "sort": True,
    }
    
def run(resource, *args, **kwargs):
    # create custom fields if needed
    create_custom_fields_as_needed()
    
    env_id = '{{ env_id }}'
    vpc_id = "{{ vpc_id }}"
    subnet_group = "{{ subnet_group }}"
    db_name = "{{ db_name }}"
    cluster_identifier = "{{ cluster_identifier }}"
    node_type = "{{ node_type }}"
    number_of_nodes = "{{ number_of_nodes }}"
    cluster_type = "{{ cluster_type }}"
    master_username = "{{ master_username }}".lower()
    master_password = "{{ master_password }}"

    env = Environment.objects.get(id=env_id)
    connection, aws_rh_id = connect_to_redshift(env)

    try:
        params = {
            "ClusterIdentifier": cluster_identifier,
            "NodeType": node_type,
            "DBName": db_name,
            "MasterUsername": master_username,
            "MasterUserPassword": master_password,
            "ClusterType": cluster_type,
            "ClusterSubnetGroupName": subnet_group,
        }
        
        if cluster_type == "multi-node":
            params["NumberOfNodes"] = int(number_of_nodes)
        
        connection.create_cluster(**params)

    except Exception as error:
        return "FAILURE", "", f"{error}"

    waiter = connection.get_waiter('cluster_available')
    set_progress("...waiting for redshift cluster to be ready...")
    waiter.wait(ClusterIdentifier=cluster_identifier)

    resource.name = cluster_identifier
    resource.env_id = env_id
    resource.aws_rh_id = aws_rh_id
    resource.vpc_id = vpc_id
    resource.subnet_group = subnet_group
    resource.node_type = node_type
    resource.master_username = master_username
    resource.master_password = master_password
    resource.cluster_type = cluster_type
    resource.cluster_name = cluster_identifier
    resource.save()

    return "SUCCESS", "Redshift Cluster created successfully.", ""