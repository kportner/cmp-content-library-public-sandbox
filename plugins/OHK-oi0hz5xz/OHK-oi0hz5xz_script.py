"""
This CloudBolt plug-in creates an auto scaling group in the VPC selected or created in a region.
Instances will be deployed in only selected zones.
Auto scaling group is also attached with the existing Application Load Balancer provided.
Scaling Policy is also created as per user inputs of metric type and target values.
"""
import ast
import base64
import json
import os
import random
import re
import time
import boto3

from django.conf import settings
from common.methods import set_progress
from infrastructure.models import CustomField, Server
from resourcehandlers.aws.models import AWSHandler
from resources.models import Resource
from servicecatalog.models import BlueprintServiceItem, ServiceBlueprint


def add_name_to_resource(**kwargs):
    client = kwargs.get('client')
    res_id = str(kwargs.get('resource_id'))
    res_name = kwargs.get('resource_name')
    response = client.create_tags(
        Resources=[res_id],
        Tags=[
            {
                'Key': 'Name',
                'Value': res_name
            },
        ]
    )
    return response


def get_or_create_custom_fields():
    CustomField.objects.get_or_create(
        name='scaling_policy_name',
        defaults={
            "label": 'Scaling Policy Name',
            "type": 'STR',
            'show_as_attribute': True,
            "description": 'Used by the AWS Auto Scaling Groups blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='metric_type',
        defaults={
            "label": 'Metric type of Auto Scaling Group',
            "type": 'STR',
            'show_as_attribute': True,
            "description": 'Used by the AWS Auto Scaling Groups blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='target_value',
        defaults={
            "label": 'Target Value of Metric',
            "type": 'INT',
            'show_as_attribute': True,
            "description": 'Used by the AWS Auto Scaling Groups blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='launch_template_name',
        defaults={
            "label": 'Launch template name',
            "type": 'STR',
            'show_as_attribute': True,
            "description": 'Used by the AWS Auto Scaling Groups blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='scaling_properties',
        defaults={
            "label": 'Scaling properties',
            "type": 'STR',
            'show_as_attribute': True,
            "description": 'Used by the AWS Auto Scaling Groups blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='health_check_period',
        defaults={
            "label": 'Health Check Grace Period',
            "type": 'INT',
            'show_as_attribute': True,
            "description": 'Used by the AWS Auto Scaling Groups blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='auto_scaling_group_name',
        defaults={
            "label": 'Auto Scaling Group Name',
            "type": 'STR',
            'show_as_attribute': False,
            "description": 'Used by the HA Architecture blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='asg_metric_type',
        defaults={
            "label": 'Metric Type of Auto Scaling Group',
            "type": 'STR',
            'show_as_attribute': False,
            "description": 'Used by the HA Architecture blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='asg_policy_targetvalue',
        defaults={
            "label": 'Target Value of Scaling Policy',
            "type": 'STR',
            'show_as_attribute': False,
            "description": 'Used by the HA Architecture blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='launch_template_id',
        defaults={
            "label": 'Launch Template Id',
            "type": 'STR',
            'show_as_attribute': False,
            "description": 'Used by the HA Architecture blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='key_name',
        defaults={
            "label": 'Key Name',
            "type": 'STR',
            'show_as_attribute': True,
            "description": "Used by the AWS Auto Scaling Group"
        }
    )
    CustomField.objects.get_or_create(
        name='key_file_name',
        defaults={
            "label": 'PEM filename',
            "type": 'STR',
            'show_as_attribute': True,
            "description": "Used by the AWS Auto Scaling Group"
        }
    )
    CustomField.objects.get_or_create(
        name='ha_instance_type',
        defaults={
            "label": 'Instance Type',
            "type": 'STR',
            'show_as_attribute': True,
            "description": "Used by the AWS Auto Scaling Group"
        }
    )
    CustomField.objects.get_or_create(
        name='ec2_key_name',
        defaults={
            "label": 'EC2 Key Name',
            "type": 'STR',
            'show_as_attribute': True,
            "description": "Used by the HA Architecture blueprint"
        }
    )
    CustomField.objects.get_or_create(
        name='ami_id',
        defaults={
            "label": 'Ami id',
            "type": 'STR',
            'show_as_attribute': True,
            "description": "Used by the HA Architecture blueprint"
        }
    )
    CustomField.objects.get_or_create(
        name='instance_type',
        defaults={
            "label": 'Instance Type',
            "type": 'STR',
            'show_as_attribute': True,
            "description": "Used by the HA Architecture blueprint"
        }
    )


def get_parent_bp(**kwargs):
    current_bp = kwargs.get('current_bp')
    bp_service_item = BlueprintServiceItem.objects.filter(
        sub_blueprint=current_bp, blueprint__status="ACTIVE"
    ).prefetch_related("blueprint").last()
    
    if bp_service_item:
        return ServiceBlueprint.objects.get(id=bp_service_item.blueprint_id) 
    return ServiceBlueprint.objects.filter(name__icontains="CloudBolt HA Deployment on AWS").first()


def generate_options_for_metric_type(control_value=None, **kwargs):
    return [
        ('ASGAverageCPUUtilization', 'Average CPU Utilization (Target Value is in %)'),
        ('ASGAverageNetworkIn', 'Average Network In (Target Value is in %)'),
        ('ASGAverageNetworkOut', 'Average Network Out (Target Value is in %)'),
        ('ALBRequestCountPerTarget', 'Request Count Per Target (Target Value is multiple of 10)'),
    ]


def get_boto3_client(aws_id, service, region=None):
    try:
        rh = AWSHandler.objects.get(id=aws_id)
        wrapper = rh.get_api_wrapper()
    except Exception:
        return None

    # See http://boto3.readthedocs.io/en/latest/guide/configuration.html#method-parameters
    client = wrapper.get_boto3_client(
        service,
        rh.serviceaccount,
        rh.servicepasswd,
        region
    )
    return client


def get_key_names(**kwargs):
    """
        This funtions returns all key name in the provided region
    """
    region = kwargs.get("region")
    rh_id = kwargs.get("rh_id")
    rh = AWSHandler.objects.get(id=rh_id)
    wrapper = rh.get_api_wrapper()
    client = wrapper.get_boto3_client('ec2', rh.serviceaccount, rh.servicepasswd, region)
    key_resp = client.describe_key_pairs()
    kp_list = [key['KeyName'] for key in key_resp.get('KeyPairs', [])]
    return kp_list


def get_ami_id_of_version_for_region(**kwargs):
    """
    Fetches AMI ID dynamically on the fly from AWS EC2 API matching the version and target region.
    Searches for both 'v2026.2.44' and '2026.2.44' naming styles.
    """
    region = kwargs.get("region")
    version = kwargs.get("Version")
    rh_id = kwargs.get("rh_id")

    if isinstance(version, str):
        version = version.strip("[]'\" ")

    ver_clean = version.lstrip("v")
    ver_with_v = f"v{ver_clean}"

    client = get_boto3_client(rh_id, 'ec2', region=region)
    if not client:
        return None

    try:
        response = client.describe_images(
            Filters=[
                {'Name': 'state', 'Values': ['available']},
                {'Name': 'name', 'Values': [f'*{ver_with_v}*', f'*{ver_clean}*']}
            ]
        )

        images = response.get('Images', [])
        if images:
            images = sorted(images, key=lambda x: x.get('CreationDate', ''), reverse=True)
            return images[0]['ImageId']
    except Exception as e:
        set_progress(f"Dynamic AWS AMI lookup encountered an error: {e}")

    return None


def run(job, *args, **kwargs):
    key_name = "{{key_name}}"
    resource = kwargs.get('resource')
    
    get_or_create_custom_fields()

    # 1. Locate parent resource
    if not resource or not resource.parent_resource_id:
        return "FAILURE", "Execution halted: Parent resource ID not found for Auto Scaling Group.", ""

    parent_resource = Resource.objects.get(id=resource.parent_resource_id)
    
    # 2. Extract values dynamically from parent custom fields
    version = parent_resource.get_value_for_custom_field('aws_ha_cb_version')
    instance_type = parent_resource.get_value_for_custom_field('aws_ha_instance_type')

    # Secondary check in blueprint_context if available
    if not version or not instance_type:
        bp_context = kwargs.get('blueprint_context', {})
        for step_name, step_data in bp_context.items():
            if isinstance(step_data, dict):
                if not version:
                    version = step_data.get('aws_ha_cb_version')
                if not instance_type:
                    instance_type = step_data.get('aws_ha_instance_type')

    # Strict Validation: Fail if user input is missing
    if not version:
        return "FAILURE", "Missing parameter: 'aws_ha_cb_version' was not selected in select_deployment_locations.", ""
    if not instance_type:
        return "FAILURE", "Missing parameter: 'aws_ha_instance_type' was not selected in select_deployment_locations.", ""

    # Clean formatting
    if isinstance(version, str):
        version = version.strip("[]'\" ")
    if isinstance(instance_type, str):
        instance_type = instance_type.strip("[]'\" ")

    if not version.startswith('v') and version.replace('.', '').isdigit():
        version = f"v{version}"

    # 3. Retrieve infrastructure configuration from parent resource
    base_name = parent_resource.base_name
    rh = AWSHandler.objects.get(id=parent_resource.aws_rh_id)
    vpc_subnet_sg_dict = ast.literal_eval(parent_resource.vpc_subnet_structure[-1])
    ha_load_balancer_name = parent_resource.ha_load_balancer_name
    target_group_arn = parent_resource.target_group_arn
    aws_ha_region = parent_resource.aws_region_ha
    fs_id = parent_resource.efs_id

    set_progress(f"Deploying user-selected CloudBolt version '{version}' on instance type '{instance_type}' in region '{aws_ha_region}'")

    vpc_id = vpc_subnet_sg_dict[aws_ha_region]['VPC'][0]
    security_group_id = vpc_subnet_sg_dict[aws_ha_region]['VPC'][-1]
    subnet_id = vpc_subnet_sg_dict[aws_ha_region]['Subnet'][0][0]
    subnet_id_list = []
    az_list = []

    client = get_boto3_client(rh.id, 'ec2', region=aws_ha_region)
    for subnet in vpc_subnet_sg_dict[aws_ha_region]['Subnet']:
        # response = client.modify_subnet_attribute(MapPublicIpOnLaunch={'Value': True },SubnetId=subnet[0])  #Perform this if subnet has this attribute MapPublicIpOnLaunch set to False
        az_list.append(subnet[-1])
        subnet_id_list.append(subnet[0])

    key_name = key_name.replace(" ", "_")
    region = aws_ha_region
    
    # 4. Create KeyPair for region
    ec2_key_name = f"{key_name}-{base_name}"
    if ec2_key_name in get_key_names(region=region, rh_id=rh.id):
        ec2_key_name = f"{ec2_key_name}{random.randrange(100, 999, 3)}"

    fname = f"{ec2_key_name}.pem"
    resp = client.create_key_pair(KeyName=ec2_key_name)
    
    # Save PEM file
    proserv_path = getattr(settings, "PROSERV_DIR", None)
    if not (os.access(proserv_path, os.X_OK | os.W_OK)):  # Check if have access to proserv directory
        os.chmod(proserv_path, 0o777)
        
    with open(f"{proserv_path}{fname}", 'w') as file:
        file.write(resp['KeyMaterial'])
    
    set_progress(f"Key pair generated: '{ec2_key_name}'")
    
    # 5. Dynamically resolve AMI ID from AWS for the exact ordered version and region
    ami_id = get_ami_id_of_version_for_region(region=region, Version=version, rh_id=rh.id)
    
    if not ami_id:
        error_msg = f"Validation Error: Could not locate a matching AWS AMI for version '{version}' in region '{region}'."
        set_progress(error_msg)
        return "FAILURE", error_msg, ""

    set_progress(f"Resolved AMI ID '{ami_id}' for version '{version}' in region '{region}'")
    
    # 6. Create EC2 Launch Template with the exact user inputs
    launch_template_name = f"LT-{base_name}"
    set_progress(f"Creating EC2 Launch Template using '{instance_type}'")
    ec2_client = get_boto3_client(rh.id, 'ec2', region=aws_ha_region)
    response = ec2_client.create_launch_template(
        LaunchTemplateName=launch_template_name,
        LaunchTemplateData={
            'ImageId': ami_id,
            'InstanceType': instance_type,
            'SecurityGroupIds': [security_group_id],
            'KeyName': ec2_key_name,
        }
    )
    launch_template_id = response['LaunchTemplate']['LaunchTemplateId']

    # 7. Create Auto Scaling Group
    set_progress("Creating Auto Scaling Group")
    auto_scaling_group_name = f"ASG-{base_name}"
    min_size = int('{{ min_size }}')
    max_size = int('{{ max_size }}')
    desired_capacity = int('{{ desired_capacity }}')
    
    # Making sure min_size <= desired_capacity < max_size
    min_size = desired_capacity if min_size > desired_capacity else min_size
    max_size = desired_capacity + 1 if max_size < desired_capacity else max_size
    health_check_period = int('{{ health_check_period }}')
    
    elbv_client = get_boto3_client(rh.id, 'elbv2', region=aws_ha_region)
    flag = True
    while flag:
        set_progress(f"Waiting for Load Balancer {ha_load_balancer_name} to become active...")
        alb_resp = elbv_client.describe_load_balancers(Names=[ha_load_balancer_name])
        lb_state = alb_resp['LoadBalancers'][0]['State']['Code']
        if lb_state == 'active':
            flag = False
            set_progress(f"Load Balancer {ha_load_balancer_name} is now active...")
        time.sleep(5)  # Waiting for 5 sec more just to be sure

    load_balancer_arn = alb_resp['LoadBalancers'][0]['LoadBalancerArn']
    auto_scaling_client = get_boto3_client(rh.id, 'autoscaling', region=aws_ha_region)
    
    set_progress(f"Creating autoscaling group '{auto_scaling_group_name}'")
    response = auto_scaling_client.create_auto_scaling_group(
        AutoScalingGroupName=auto_scaling_group_name,
        LaunchTemplate={'LaunchTemplateId': launch_template_id},
        MinSize=min_size,
        MaxSize=max_size,
        DesiredCapacity=desired_capacity,
        HealthCheckGracePeriod=health_check_period,
        VPCZoneIdentifier=",".join(subnet_id_list),
        AvailabilityZones=az_list,
    )

    time.sleep(3)  # Initial waiting period
    
    flag = True
    while flag:
        set_progress("Fetching instances from Auto Scaling Group")
        as_resp = auto_scaling_client.describe_auto_scaling_groups(AutoScalingGroupNames=[auto_scaling_group_name])
        instance_ids = [inst['InstanceId'] for inst in as_resp['AutoScalingGroups'][0]['Instances']]
        if len(instance_ids) == desired_capacity:  # Making sure all instances are fetched
            flag = False
            set_progress(f"Fetched {len(instance_ids)} instances from Auto Scaling Group...")
        else:
            time.sleep(3)

    ec2_resource = boto3.resource(
        service_name='ec2', region_name=aws_ha_region,
        aws_access_key_id=rh.serviceaccount, aws_secret_access_key=rh.servicepasswd
    )

    instance_number = 1
    for instance_ID in instance_ids:    
        flag = True
        while flag:
            current_instance = ec2_resource.Instance(instance_ID)
            set_progress(f"Waiting for instance {instance_ID} to start running...")
            time.sleep(5)
            if current_instance.state['Name'] == 'running':
                flag = False
                set_progress(f"Instance {instance_ID} is now in running state...")
                time.sleep(5)  # Sleeping for another 5 secs for precaution
        #resp_reg_tg = elbv_client.register_targets( TargetGroupArn=TG_arn , Targets=[{ 'Id': instance_ID, }, ],)
        
        instance_name = f"{base_name}-instance-{instance_number}"
        add_name_resp = add_name_to_resource(client=ec2_client, resource_id=instance_ID, resource_name=instance_name)
        instance_number += 1

    # Number of instances equals to desired capacity will be stopped from shrinking if scale in protection is turned ON
    # response = auto_scaling_client.set_instance_protection(AutoScalingGroupName=auto_scaling_group_name,InstanceIds=instance_ids,ProtectedFromScaleIn=True)
        
    set_progress("Creating Scaling Policy")
    scaling_policy_name = f"SP-{base_name}"
    metric_type = '{{ metric_type }}'
    target_value = int('{{ target_value }}')
    
    temp_target_value = int(target_value) * 10 if metric_type in ["ALBRequestCountPerTarget"] else target_value
    if target_value < 90:
        target_value = 90  # Deliberately setting target value to 90%/900 so that autoscalinggroup wont shrink instances during setup, will undo this in last plugin

    if metric_type == "ALBRequestCountPerTarget":
        resource_label = f'''{"/".join(load_balancer_arn.split("/")[1:])}/targetgroup/{"/".join(target_group_arn.split("/")[1:])}''' #if metric_type == "ALBRequestCountPerTarget" else None
        target_value = target_value * 10  # optimal average request count per instance during any one-minute interval
        predefined_metric_specification = {'PredefinedMetricType': metric_type, 'ResourceLabel': resource_label}
        set_progress("finally attaching Load Balancer with Auto Scaling Group")
        resp = auto_scaling_client.attach_load_balancer_target_groups(
            AutoScalingGroupName=auto_scaling_group_name, TargetGroupARNs=[target_group_arn]
        ) 
    else:
        predefined_metric_specification = {'PredefinedMetricType': metric_type}

    auto_scaling_client.put_scaling_policy(
        AutoScalingGroupName=auto_scaling_group_name,
        PolicyName=scaling_policy_name,
        PolicyType='TargetTrackingScaling',
        AdjustmentType='ChangeInCapacity',
        TargetTrackingConfiguration={
            'PredefinedMetricSpecification': predefined_metric_specification,
            'TargetValue': target_value
        },
    )

    set_progress(f"Target Value set as '{temp_target_value}'")
    set_progress(f"Scaling Configuration set as Minimum Size: {min_size}, Maximum Size: {max_size}, Desired Capacity: {desired_capacity}")

    #set_progress("finally attaching Load Balancer with Auto Scaling Group")
    #ASB_LB_resp = auto_scaling_client.attach_load_balancer_target_groups(AutoScalingGroupName=auto_scaling_group_name, TargetGroupARNs=[target_group_arn],)  # This step is done in last plugin of HA_Architecture to avoid excess load of health-check

    # Persist values onto resources
    parent_resource.auto_scaling_group_name = auto_scaling_group_name
    parent_resource.launch_template_id = launch_template_id
    parent_resource.asg_metric_type = metric_type
    parent_resource.asg_policy_targetvalue = temp_target_value
    parent_resource.ami_id = ami_id
    parent_resource.ec2_key_name = ec2_key_name
    parent_resource.instance_type = instance_type
    parent_resource.save()

    resource.name = auto_scaling_group_name
    resource.key_name = ec2_key_name
    resource.key_file_name = fname
    resource.ha_instance_type = instance_type
    resource.scaling_policy_name = scaling_policy_name
    resource.metric_type = metric_type
    resource.target_value = temp_target_value  # We are making it 90%/900 for now, change it at the end
    resource.scaling_properties = f"Minimum Size : {min_size}, Maximum Size : {max_size}, Desired Capacity : {desired_capacity}"
    resource.health_check_period = health_check_period
    resource.save()

    return "SUCCESS", "Auto Scaling Group with scaling Policy created successfully", ""