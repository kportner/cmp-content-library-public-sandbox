from resourcehandlers.aws.models import AWSHandler
from common.methods import set_progress
from servicecatalog.models import ServiceBlueprint
from infrastructure.models import CustomField
from resources.models import Resource, ResourceType
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


def run(job, resource, *args, **kwargs):
    set_progress("Connecting to EC2 EBS")
    volume_id = resource.attributes.get(field__name='ebs_volume_id').value
    rh_id = resource.attributes.get(field__name='aws_rh_id').value
    region = resource.attributes.get(field__name='aws_region').value
    handler = AWSHandler.objects.get(id=rh_id)

    ec2 = get_boto3_service_resource(handler, region)

    create_custom_fields()

    volume = ec2.Volume(volume_id)
    snapshot_iterator = volume.snapshots.all()

    blueprint = ServiceBlueprint.objects.filter(name__icontains="snapshots").first()
    group = Group.objects.first()
    resource_type = ResourceType.objects.filter(name__icontains="Snapshot").first()
    if not resource_type:
        resource_type = ResourceType.objects.create(name="snapshot", label="Snapshot")
        
    for snap in snapshot_iterator:
        set_progress(snap.state)
        snap.reload()
        res, created = Resource.objects.get_or_create(
            name=snap.id,
            blueprint_id=resource.blueprint_id,
            defaults={
                'description': snap.description,
                'blueprint': blueprint,
                'group': group,
                'parent_resource': resource,
                'lifecycle': snap.state,
                'resource_type': resource_type})
        if not created:
            res.description = snap.description
            res.group = group
            res.parent_resource = resource
            res.lifecycle = snap.state
            res.resource_type = resource_type
            if blueprint:
                res.blueprint = blueprint

            res.save()
        res.start_time = snap.start_time.isoformat(' ', timespec='seconds')
        res.save()

    return "SUCCESS", "", ""