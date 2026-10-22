from resourcehandlers.aws.models import AWSHandler
import time
from common.methods import set_progress
from servicecatalog.models import ServiceBlueprint
from resources.models import Resource, ResourceType
from infrastructure.models import CustomField
from accounts.models import Group

def create_custom_fields():
    """
    create custom fields
    """
    CustomField.objects.get_or_create(
        name='start_time', type='STR',
        defaults={'label':'Snapshot Start Time', 'description':'Time when the snapshot was taken', 'show_as_attribute':True, 'show_on_servers':True}
    )

def get_boto3_service_resource(rh: AWSHandler, aws_region, service_name="ec2"):
    """
    Return boto connection to the EC2 in the specified environment's region.
    """

    # get aws client object
    client = rh.get_boto3_resource(aws_region, service_name)
    return client

def run(resource, *args, **kwargs):
    set_progress("Connecting to EC2")
    handler = AWSHandler.objects.get(id=resource.aws_rh_id)
    set_progress("This resource belongs to {}".format(handler))

    volume_id = resource.attributes.get(field__name='ebs_volume_id').value
    rh_id = resource.attributes.get(field__name='aws_rh_id').value
    region = resource.attributes.get(field__name='aws_region').value
    handler = AWSHandler.objects.get(id=rh_id)
    blueprint = ServiceBlueprint.objects.filter(name__icontains="snapshots").first()
    group = Group.objects.first()
    resource_type = ResourceType.objects.filter(name__icontains="Snapshot").first()
    if not resource_type:
        resource_type = ResourceType.objects.create(name="snapshot", label="Snapshot")
    ec2 = get_boto3_service_resource(handler, region)
    volume = ec2.Volume(volume_id)

    snapshot = volume.create_snapshot(
        Description='Volume Snapshot for {}'.format(volume_id),
    )
    state = snapshot.state
    count = 0
    while state !='completed':
        set_progress(f"Creating snapshot...")
        count +=5
        time.sleep(5)
        snapshot.reload()
        state = snapshot.state
        if count > 3600:
            # Taking snapshot os taking too long
            return "FAILURE", "Failed to take a snapshot", "Snapshot taking took too long."

    create_custom_fields()
    
    # Save the snapshot to the list of available snapshots
    resource, _ = Resource.objects.get_or_create(
        name=snapshot.id,
        blueprint_id=resource.blueprint_id,
        defaults={
            'description': snapshot.description,
            'blueprint': blueprint,
            'group': group,
            'parent_resource': resource,
            'lifecycle': snapshot.state,
            'resource_type': resource_type})
    resource.start_time = snapshot.start_time.isoformat(' ', timespec='seconds')
    resource.save()
    return "SUCCESS", "", ""