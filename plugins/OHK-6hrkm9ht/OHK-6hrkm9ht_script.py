"""
Build service item action for AWS security group.
"""
from common.methods import set_progress
from infrastructure.models import CustomField, Environment
from resourcehandlers.aws.models import AWSHandler
from botocore.exceptions import ClientError
from accounts.models import Group


def get_boto3_service_client(rh: AWSHandler, aws_region, service_name="ec2"):
    """
    Return boto connection to the EC2 in the specified environment's region.
    """
    # get aws client object
    client = rh.get_boto3_client(aws_region, service_name)

    return client


def generate_options_for_region(**kwargs):
    group_name = kwargs["group"]
    options = [("", "---Select Region---")]
    try:
        group = Group.objects.get(name=group_name)
    except Exception as err:
        return options
    # fetch all group environment
    envs = group.get_available_environments()
    aws_envs= [(str(env.id), env.name) for env in envs if env.resource_handler is not None and env.resource_handler.resource_technology.slug.startswith('aws')]
    if len(aws_envs):
        return aws_envs
    else:
        return options


def generate_options_for_vpc_id(control_value=None, **kwargs):
    if control_value is None or control_value=="":
        return [("", "---Select Vpc ID---")]
    env = Environment.objects.get(id=control_value)
    rh = env.resource_handler.cast()
    ec2_client = get_boto3_service_client(rh, env.aws_region)
    response = ec2_client.describe_vpcs()
    vpcs = response['Vpcs']
    return [(r['VpcId']) for r in vpcs]


def generate_options_for_direction(**kwargs):
    return ['Ingress', 'Egress']


def generate_options_for_ip_protocol(**kwargs):
    return ['tcp', 'udp', 'icmp']


def generate_custom_fields_as_needed():
    CustomField.objects.get_or_create(
        name='aws_rh_id', type='STR',
        defaults={'label': 'AWS RH ID',
                  'description': 'Used by the AWS blueprints'}
    )
    CustomField.objects.get_or_create(
        name='aws_region', type='STR',
        defaults={'label': 'AWS Region',
                  'description': 'Used by the AWS blueprints', 'show_as_attribute': True}
    )
    CustomField.objects.get_or_create(
        name='security_group_name', type='STR',
        defaults={'label': 'AWS security group name',
                  'description': 'Used by the AWS security group blueprint', 'show_as_attribute': True}
    )
    CustomField.objects.get_or_create(
        name='security_group_description', type='STR',
        defaults={'label': 'AWS security group description',
                  'description': 'AWS security group description', 'show_as_attribute': True}
    )
    CustomField.objects.get_or_create(
        name='security_group_id', 
        type='STR',
        defaults={'label': 'AWS Security group ID',
                  'description': 'AWS Security group ID'}
    )


def run(job, logger=None, **kwargs):

    generate_custom_fields_as_needed()
    
    env = Environment.objects.get(id='{{ region }}')
    rh = env.resource_handler.cast()
    
    vpc_id = "{{ vpc_id }}"
    security_group_name = "{{ security_group_name }}"
    security_group_description = "{{ security_group_description }}"
    direction = "{{ direction }}"
    ip_protocol = "{{ ip_protocol }}"
    from_port = "{{ from_port }}"
    to_port = "{{ to_port }}"
    cidr_ip = "{{ cidr_ip }}"

    set_progress('Connecting to Amazon EC2')
    ec2_client = get_boto3_service_client(rh, env.aws_region )

    set_progress('Create EC2 security group')

    try:
        response = ec2_client.create_security_group(GroupName=security_group_name,
                                                    Description=security_group_description,
                                                    VpcId=vpc_id)
        security_group_id = response['GroupId']
        set_progress('Security Group Created %s in vpc %s.' %
                     (security_group_id, vpc_id))

        if direction == 'Ingress':
            data = ec2_client.authorize_security_group_ingress(
                GroupId=security_group_id,
                IpPermissions=[
                    {'IpProtocol': ip_protocol,
                     'FromPort': int(from_port),
                     'ToPort': int(to_port),
                     'IpRanges': [{'CidrIp': cidr_ip}]}
                ])
            set_progress('Ingress Successfully Set %s' % data)
        elif direction == 'Egress':
            data = ec2_client.authorize_security_group_egress(
                GroupId=security_group_id,
                IpPermissions=[
                    {'IpProtocol': ip_protocol,
                     'FromPort': int(from_port),
                     'ToPort': int(to_port),
                     'IpRanges': [{'CidrIp': cidr_ip}]}
                ])
            set_progress('Ingress Successfully Set %s' % data)
    except ClientError as e:
        return "FAILURE", "The security group could not be created. Reason: ", e

    resource = kwargs.get('resource')
    resource.name = security_group_name + " - " + security_group_id
    resource.aws_region = env.aws_region
    resource.aws_rh_id = rh.id
    resource.security_group_name = security_group_name + " - " + security_group_id
    resource.security_group_description = security_group_description
    resource.security_group_id = security_group_id
    resource.save()

    return "SUCCESS", "The security group was created successfully", ""