from common.methods import set_progress
from resourcehandlers.aws.models import AWSHandler
from resources.models import Resource

def get_boto3_client(service_name='ec2',**kwargs):
    region = None
    rh = kwargs.get('resource_handler')
    region = kwargs.get('region', None)
    service_name = kwargs.get('service')
    wrapper = rh.get_api_wrapper()
    return wrapper.get_boto3_client(service_name, rh.serviceaccount, rh.servicepasswd , region)

def generate_options_for_old_scaling_configuration(**kwargs):
    resource = kwargs.get('resource') 
    if resource:
        sub_resource = Resource.objects.filter(parent_resource_id=resource.id,name__icontains = resource.auto_scaling_group_name).first()
        if sub_resource:
            return [("",sub_resource.scaling_properties)]
    else:
        return [("","--can't fetch old scaling properties--")]
    
def run(job, *args, **kwargs):
    old_scaling_configuration = "{{old_scaling_configuration}}"
    min_size = int('{{ min_size }}')
    max_size = int('{{ max_size }}')    
    desired_capacity = int('{{ desired_capacity }}')
    min_size = desired_capacity if min_size > desired_capacity else min_size
    max_size = desired_capacity+1 if max_size < desired_capacity else max_size
    resource = kwargs.get('resource') 
    base_name = resource.base_name
    aws_ha_region = resource.aws_region_ha
    rh = AWSHandler.objects.get(id = resource.aws_rh_id)
    auto_scaling_client = get_boto3_client(service='autoscaling', resource_handler = rh, region=aws_ha_region)
    try:
        response = auto_scaling_client.update_auto_scaling_group(
            AutoScalingGroupName=resource.auto_scaling_group_name,
            MinSize=min_size,
            MaxSize=max_size,
            DesiredCapacity=desired_capacity,
        )
    except:
        set_progress(f"Changing scaling confiuration for {resource.auto_scaling_group_name} has failed")
    
    
    sub_resource = Resource.objects.filter(parent_resource_id=resource.id,name__icontains = resource.auto_scaling_group_name).first()
    if sub_resource:
        sub_resource.scaling_properties = f"Minimum Size : {min_size}, Maximum Size : {max_size}, Desired Capacity : {desired_capacity}"
        sub_resource.save()
        
    set_progress(f"Successfully changed scaling confiuration for {resource.auto_scaling_group_name}")