"""
Plugin: SageMaker!

Description:
---------------
This plugin is a simple example that launches a AWS SageMaker notebook instance for a given AWS RH

** See Readme for Blueprint details **

"""
from common.methods import set_progress
from infrastructure.models import CustomField, Environment
from resourcehandlers.aws.models import AWSHandler
from botocore.exceptions import ClientError


###
# AWS Environment Dropdown
###
def generate_options_for_env_id(profile=None, **kwargs):
    group = kwargs["group"]
    # fetch all group environment
    envs = group.get_available_environments()
    options = [(env.id, env.name) for env in envs if env.resource_handler is not None and env.resource_handler.resource_technology.slug.startswith('aws')]
    return options


###
# Get boto3 client
###
def get_boto_client(env_id=None, boto_service=''):
    if env_id == None:
        return None
    env = Environment.objects.get(id=env_id)
    rh: AWSHandler = env.resource_handler.cast()
    client = rh.get_boto3_client(env.aws_region, boto_service)
    return client, env

###
# Subnet Dropdown
###
def generate_options_for_subnet(control_value=None, profile=None, **kwargs):
    options = []
    if control_value is not None:
        client, env = get_boto_client(control_value, 'ec2')
        response = client.describe_subnets(Filters=[
            {
                'Name': 'state',
                'Values': ['available']
            },
            {
                'Name': 'vpc-id',
                'Values': [env.vpc_id]
            }
        ])
        subnets = response['Subnets']
        for subnet in subnets:
            options.append(subnet['SubnetId'])
    return options

###
# Security Group
###
def generate_options_for_securitygroup(control_value=None, profile=None, **kwargs):
    options = []
    if control_value is not None:
        client, env = get_boto_client(control_value, 'ec2')
        response = client.describe_security_groups(
            Filters=[
                {
                    'Name': 'vpc-id',
                    'Values': [env.vpc_id]
                }
            ]
        )
        sgs = response['SecurityGroups']
        for sg in sgs:
            options.append(sg['GroupId'])
    return options


###
# Role
###
def generate_options_for_role(control_value=None, profile=None, **kwargs):
    options = []
    if control_value is None:
        return options

    client, _ = get_boto_client(control_value, 'iam')
    response = client.list_roles()
    roles = response['Roles']
    for role in roles:
        if role['Arn'].lower().find('sage') >= 0:
            options.append((role['Arn'], role['RoleName']))
    return options


###
# Instance Size
###
def generate_options_for_instance_type(control_value=None, profile=None, **kwargs):
    return ["ml.t2.medium", "ml.t2.large", "ml.t2.xlarge", "ml.t2.2xlarge", "ml.t3.medium"]


###
# Create custom fields
###
def create_custom_fields():
    CustomField.objects.get_or_create(
        name='aws_rh_id',
        defaults={
            "label": 'AWS RH ID',
            "type": 'STR',
        }
    )

    CustomField.objects.get_or_create(
        name='aws_env_id',
        defaults={
            "label": 'AWS Env ID',
            "type": 'STR',
        }
    )
    CustomField.objects.get_or_create(
        name='aws_region',
        defaults={
            "label": 'AWS Region ID',
            "type": 'STR',
        }
    )
    CustomField.objects.get_or_create(
        name='sagemaker_notebook_instance_name', type='STR',
        defaults={'label': 'Notebook Name',
                  'description': 'Used by the Amazon Sagemaker blueprint', 'show_as_attribute': True}
    )
    CustomField.objects.get_or_create(
        name='sagemaker_notebook_instance_arn', type='STR',
        defaults={'label': 'Notebook ARN',
                  'description': 'Used by the Amazon Sagemaker blueprint', 'show_as_attribute': True}
    )


###
# Main Run Method
###
def run(resource, logger=None, **kwargs):

    create_custom_fields()

    # 1. Grab/define vars
    env_id = '{{ env_id }}'
    subnet = '{{ subnet }}'
    security_group = '{{ securitygroup }}'
    role = '{{ role }}'
    instance_type = '{{ instance_type }}'
    notebook_instance_name = '{{ notebook_instance_name_input }}'

    env = Environment.objects.get(id=env_id)
    region = env.aws_region
    rh = env.resource_handler.cast()

    set_progress("Connection to Amazon Sagemaker...")

    client, env = get_boto_client(env_id, 'sagemaker')

    set_progress("Creating Sagemaker notebook instance - {}".format(notebook_instance_name))

    try:
        response = client.create_notebook_instance(
            NotebookInstanceName=notebook_instance_name,
            InstanceType=instance_type,
            SubnetId=subnet,
            SecurityGroupIds=[
                security_group,
            ],
            RoleArn=role,
        )

        # Set bits on resource
        resource.aws_region = region
        resource.aws_rh_id = rh.id
        resource.aws_env_id = env_id
        resource.sagemaker_notebook_instance_name = notebook_instance_name
        resource.sagemaker_notebook_instance_arn = response['NotebookInstanceArn']
        resource.save()

    except ClientError as e:
        resource.delete()
        set_progress('AWS ClientError: {}'.format(e))
        return "FAILURE", "", e
    except Exception as err:
        return "FAILURE", "Amazon Sagemaker Instance could not be created", str(err)

    return "SUCCESS", "Amazon Sagemaker Instance created successfully", ""