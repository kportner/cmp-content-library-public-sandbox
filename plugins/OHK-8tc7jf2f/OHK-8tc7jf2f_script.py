"""
Build service item action for AWS EBS Volume blueprint.
"""
from common.methods import set_progress
from infrastructure.models import CustomField
from infrastructure.models import Environment
from django.db import IntegrityError
from accounts.models import Group
from resourcehandlers.aws.models import AWSHandler

    
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


def generate_options_for_volume_type(server=None, **kwargs):
    return [
        ('gp2', 'General Purpose SSD'),
        ('io1', 'Provisioned IOPS SSD'),
        ('sc1', 'Cold HDD'),
        ('st1', 'Throughput Optimized HDD'),
        ('standard', 'Magnetic'),
    ]


def get_boto3_service_client(env, service_name="ec2"):
    """
    Return boto connection to the EC2 in the specified environment's region.
    """
    # get aws resource handler object
    rh: AWSHandler = env.resource_handler.cast()

    # get aws client object
    client = rh.get_boto3_client(env.aws_region, service_name)

    return client

def create_custom_fields():
    """
    create custom fields
    """
    CustomField.objects.get_or_create(
        name='aws_rh_id', type='STR',
        defaults={'label':'AWS RH ID', 'description':'Used by the AWS blueprints'}
    )
    aws_region, _ = CustomField.objects.get_or_create(
        name='aws_region', type='STR',
        defaults={'label':'AWS Region', 'description':'Used by the AWS blueprints', 'show_as_attribute':True, 'show_on_servers':True}
    )
    if aws_region.show_on_servers == False:
        aws_region.show_on_servers = True
        aws_region.show_as_attribute = True
        aws_region.save()
    CustomField.objects.get_or_create(
        name='ebs_volume_id', type='STR',
        defaults={'label':'AWS Volume ID', 'description':'Used by the AWS blueprints', 'show_as_attribute':True}
    )
    CustomField.objects.get_or_create(
        name='ebs_volume_size', type='INT',
        defaults={'label':'Volume Size (GB)', 'description':'Used by the AWS blueprints', 'show_as_attribute':True}
    )
    CustomField.objects.get_or_create(
        name='volume_encrypted', type='BOOL',
        defaults={'label':'Encrypted', 'description':'Whether this volume is encrypted or not', 'show_as_attribute':True}
    )
    CustomField.objects.get_or_create(
        name='volume_state', type='STR',
        defaults={'label': 'Volume status', 'description': 'Current state of the volume.',
                  'show_as_attribute': True}
    )
    CustomField.objects.get_or_create(
        name='instance_id', type='STR',
        defaults={'label': 'Instance attached to', 'description': 'The instance this volume is attached to',
                  'show_as_attribute': True}
    )
    CustomField.objects.get_or_create(
        name='device_name', type='STR',
        defaults={'label': 'Device name', 'description': 'The name of the device this volume is attached to',
                  'show_as_attribute': True}
    )

def run(job, logger=None, **kwargs):

    env_id = '{{ env_id }}'
    volume_name = '{{ volume_name }}'
    env = Environment.objects.get(id=env_id)
    rh = env.resource_handler.cast()
    volume_type = '{{ volume_type }}'
    encrypted = bool('{{ encrypted }}')

    # Constraints: 1-16384 for gp2, 4-16384 for io1, 500-16384 for st1,
    # 500-16384 for sc1, and 1-1024 for standard.
    # This plug-in limits all values to: 1-16384.
    volume_size_gb = int('{{ volume_size_gb }}')
    
    create_custom_fields()
    
    set_progress('Connecting to Amazon EC2')
    ec2 = get_boto3_service_client(env)

    set_progress('Creating EBS volume...')
    volume_dict = ec2.create_volume(
        Size=volume_size_gb,
        AvailabilityZone=env.aws_availability_zone,
        VolumeType=volume_type,
        Encrypted=encrypted,
        TagSpecifications=[
            {
                'ResourceType': 'volume',
                'Tags': [
                    {
                        'Key': 'Name',
                        'Value': volume_name
                    }
                ]
            }
        ]
    )
    volume_id = volume_dict['VolumeId']

    resource = kwargs.pop('resources').first()
    resource.name = volume_name
    resource.ebs_volume_id = volume_id
    resource.ebs_volume_size = volume_size_gb
    resource.aws_region = env.aws_region
    resource.aws_rh_id = rh.id
    resource.volume_encrypted = encrypted

    set_progress('Waiting for volume to become available...')
    waiter = ec2.get_waiter('volume_available')
    waiter.wait(VolumeIds=[volume_id])

    resource.volume_state = "available"
    resource.instance_id = "N/A"
    resource.device_name = "N/A"
    resource.save()

    set_progress('Volume ID "{}" is now available'.format(volume_id))

    return "SUCCESS", "", ""