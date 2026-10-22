from common.methods import set_progress
from resourcehandlers.aws.models import AWSHandler

def get_boto3_client(service_name='ec2',**kwargs):
    region = None
    rh = kwargs.get('resource_handler')
    region = kwargs.get('region', None)
    service_name = kwargs.get('service')
    wrapper = rh.get_api_wrapper()
    return wrapper.get_boto3_client(service_name, rh.serviceaccount, rh.servicepasswd , region)

def generate_options_for_metric_type(**kwargs):
    resource = kwargs.get('resource')
    if resource.asg_metric_type in ["ALBRequestCountPerTarget"]:
        return [('ALBRequestCountPerTarget', 'Request Count Per Target (Target Value is multiple of 10)')]
    else:
        return [(resource.asg_metric_type,resource.asg_metric_type)]
    
def generate_options_for_old_threshold_value(**kwargs):
    resource = kwargs.get('resource') 
    if resource:
        return [("",resource.asg_policy_targetvalue)]

def run(job, *args, **kwargs):
    metric_type = "{{metric_type}}"
    target_value = "{{threshold_value}}"
    old_threshold_value  = "{{old_threshold_value}}"
    resource = kwargs.get('resource') 
    base_name = resource.base_name
    aws_ha_region = resource.aws_region_ha
    rh = AWSHandler.objects.get(id = resource.aws_rh_id)
    load_balancer_arn = resource.ha_load_balancer_arn
    target_group_arn = resource.target_group_arn
    auto_scaling_client = get_boto3_client(service='autoscaling', resource_handler = rh, region=aws_ha_region)
    if resource.asg_metric_type in ["ALBRequestCountPerTarget"]:
        resource_label = f'''{"/".join(load_balancer_arn.split("/")[1:])}/targetgroup/{"/".join(target_group_arn.split("/")[1:])}''' #if metric_type == "ALBRequestCountPerTarget" else None
        target_value = int(target_value)*10 # optimal average request count per instance during any one-minute interval
        predefined_metric_specification = {'PredefinedMetricType': resource.asg_metric_type,'ResourceLabel': resource_label}
    else:
        predefined_metric_specification = {'PredefinedMetricType': resource.asg_metric_type}
    try:
        auto_scaling_client.put_scaling_policy(
                AutoScalingGroupName=resource.auto_scaling_group_name,
                PolicyName=f"SP-{base_name}",
                PolicyType='TargetTrackingScaling',
                AdjustmentType='ChangeInCapacity',
                TargetTrackingConfiguration={
                    'PredefinedMetricSpecification': predefined_metric_specification,
                    'TargetValue': int(target_value)
                },
            )
    except:
        set_progress(f"Changing threshold value from {resource.asg_policy_targetvalue} to {target_value} is failed")
    else:
        set_progress(f"Successfully changed threshold value from {resource.asg_policy_targetvalue} to {target_value}")    
    resource.asg_policy_targetvalue = target_value
    resource.save()