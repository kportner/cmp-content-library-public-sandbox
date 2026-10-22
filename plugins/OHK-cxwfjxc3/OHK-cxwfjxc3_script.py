"""
This plugin is used to teardown an autoscaling group and all of its dependencies

This plug-in deletes following resources:
- Autoscaling Group
- Launch Template
- Load Balancer
- Target Group
- Listener
- Scaling Policy

The following parameters are required to be set on the resource:
- aws_asg_environment_id
- aws_launch_template_id
- aws_asg_name
- aws_lb_arn
- aws_target_group_arn
- aws_listener_arn
- aws_scaling_policy_name
"""

from common.methods import set_progress
from infrastructure.models import Environment
from utilities.logger import ThreadLogger
from resourcehandlers.aws.models import AWSHandler

logger = ThreadLogger(__name__)


def get_boto3_client(rh: AWSHandler, service, region=None):
    client = rh.get_boto3_client(region, service)
    return client


def run(job, resource=None, *args, **kwargs):
    if not resource:
        return "FAILURE", "No resource provided", ""
    env = Environment.objects.get(id=resource.aws_asg_environment_id)
    rh = env.resource_handler.cast()

    aws_launch_template_id = resource.aws_launch_template_id
    aws_asg_name = resource.aws_asg_name
    aws_lb_arn = resource.aws_lb_arn
    aws_target_group_arn = resource.aws_target_group_arn
    aws_listener_arn = resource.aws_listener_arn
    aws_scaling_policy_name = resource.aws_scaling_policy_name

    # Delete Autoscaling Group and Scaling Policy
    delete_autoscaling_group(env, rh, aws_asg_name, aws_scaling_policy_name)

    # Delete Load Balancer, Target Group, and Listener
    delete_load_balancer(env, rh, aws_lb_arn, aws_target_group_arn,
                         aws_listener_arn)

    # Delete Launch Template
    delete_launch_template(env, rh, aws_launch_template_id)


def delete_autoscaling_group(env, rh, aws_asg_name, aws_scaling_policy_name):
    client = get_boto3_client(rh, "autoscaling", env.aws_region)
    if aws_scaling_policy_name and aws_asg_name:
        set_progress(f"Deleting Scaling Policy: {aws_scaling_policy_name}")
        try:
            client.delete_policy(
                AutoScalingGroupName=aws_asg_name,
                PolicyName=aws_scaling_policy_name
            )
        except Exception as e:
            if str(type(e)).find("NotFound"):
                set_progress("LB not found, assuming already deleted.")
            else:
                raise e
    else:
        set_progress("No Scaling Policy to delete")
    if aws_asg_name:
        set_progress(f"Deleting Autoscaling Group: {aws_asg_name}")
        try:
            client.delete_auto_scaling_group(
                AutoScalingGroupName=aws_asg_name, ForceDelete=True
            )
        except Exception as e:
            if str(type(e)).find("NotFound"):
                set_progress("ASG not found, assuming already deleted.")
            else:
                raise e
    else:
        set_progress("No Autoscaling Group to delete")


def delete_load_balancer(env, rh, aws_lb_arn, aws_target_group_arn,
                         aws_listener_arn):
    client = get_boto3_client(rh, "elbv2", env.aws_region)
    if aws_listener_arn:
        set_progress(f"Deleting Listener: {aws_listener_arn}")
        try:
            client.delete_listener(ListenerArn=aws_listener_arn)
        except Exception as e:
            if str(type(e)).find("NotFound"):
                set_progress("Listener not found, assuming already deleted.")
            else:
                raise e
    else:
        set_progress("No Listener to delete")
    if aws_target_group_arn:
        set_progress(f"Deleting Target Group: {aws_target_group_arn}")
        try:
            client.delete_target_group(TargetGroupArn=aws_target_group_arn)
        except Exception as e:
            if str(type(e)).find("NotFound"):
                set_progress("Target Group not found, assuming already "
                             "deleted.")
            else:
                raise e
    else:
        set_progress("No Target Group to delete")
    if aws_lb_arn:
        set_progress(f"Deleting Load Balancer: {aws_lb_arn}")
        try:
            client.delete_load_balancer(LoadBalancerArn=aws_lb_arn)
        except Exception as e:
            if str(type(e)).find("NotFound"):
                set_progress("LB not found, assuming already deleted.")
            else:
                raise e
    else:
        set_progress("No Load Balancer to delete")


def delete_launch_template(env, rh, aws_launch_template_id):
    client = get_boto3_client(rh, "ec2", env.aws_region)
    if aws_launch_template_id:
        set_progress(f"Deleting Launch Template: {aws_launch_template_id}")
        try:
            client.delete_launch_template(
                LaunchTemplateId=aws_launch_template_id
            )
        except Exception as e:
            if str(type(e)).find("NotFound"):
                set_progress("Launch Template not found, assuming already "
                             "deleted.")
            else:
                raise e
    else:
        set_progress("No Launch Template to delete")