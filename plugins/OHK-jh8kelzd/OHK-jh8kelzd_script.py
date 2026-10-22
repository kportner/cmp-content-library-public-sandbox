from common.methods import set_progress
from resourcehandlers.aws.models import AWSHandler
from infrastructure.models import CustomField

RESOURCE_IDENTIFIER = 'ebs_volume_id'

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

def get_boto3_service_resource(rh: AWSHandler, aws_region, service_name="ec2"):
    """
    Return boto connection to the EC2 in the specified environment's region.
    """

    # get aws client object
    client = rh.get_boto3_resource(aws_region, service_name)

    return client

def discover_resources(**kwargs):
    discovered_volumes = []
    create_custom_fields()
    for handler in AWSHandler.objects.all():
        set_progress('Connecting to Amazon EC2 for handler: {}'.format(handler))
        for region in handler.current_regions():
            ec2 = get_boto3_service_resource(handler, region)
            try:
                for volume in ec2.volumes.all():
                    if len(volume.attachments) > 0:
                        instance_id = volume.attachments[0].get('InstanceId')
                        device_name = volume.attachments[0].get('Device')
                    else:
                        instance_id = "N/A"
                        device_name = "N/A"

                    discovered_volumes.append({
                        'name': f"EBS Volume - {volume.volume_id}",
                        'ebs_volume_id': volume.volume_id,
                        "aws_rh_id": handler.id,
                        "aws_region": region,
                        "volume_state": volume.state,
                        "ebs_volume_size": volume.size,
                        "volume_encrypted": volume.encrypted,
                        "instance_id": instance_id,
                        "device_name": device_name,
                    })

            except Exception as e:
                set_progress('AWS ClientError: {}'.format(e))
                continue

    return discovered_volumes