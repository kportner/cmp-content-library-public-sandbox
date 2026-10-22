"""
This CloudBolt plugin creates an AWS Application Load Balancer with HTTPS and HTTP Listeners.
It diverts all HTTP (port 80) traffic to HTTPS (port-no 443).
The HTTPS listener requires an ACM certificate associated with the FQDN.
"""
import ast
import os
import re
import time
import boto3

from django.conf import settings
from common.methods import set_progress
from infrastructure.models import CustomField
from orders.models import Order
from resourcehandlers.aws.models import AWSHandler
from resources.models import Resource
from servicecatalog.models import BlueprintServiceItem, ServiceBlueprint


def get_or_create_custom_fields():
    CustomField.objects.get_or_create(
        name='ha_load_balancer_name',
        defaults={
            "label": 'AWS Load Balancer',
            "type": 'STR',
            'show_as_attribute': False,
            "description": "Used by the HA Architecture blueprint"
        }
    )
    CustomField.objects.get_or_create(
        name='ha_load_balancer_arn',
        defaults={
            "label": 'AWS Load Balancer ARN',
            "type": 'STR',
            'show_as_attribute': False,
            "description": "Used by the HA Architecture"
        }
    )
    CustomField.objects.get_or_create(
        name='ha_acm_certificate_arn',
        defaults={
            "label": 'ACM Certificate ARN',
            "type": 'STR',
            'show_as_attribute': False,
            "description": "Used by the HA Architecture"
        }
    )
    CustomField.objects.get_or_create(
        name='load_balancer_name',
        defaults={
            "label": 'AWS Load Balancer Name',
            "type": 'STR',
            'show_as_attribute': True,
            "description": "Used by the HA Architecture's AWS HA Load Balancer"
        }
    )
    CustomField.objects.get_or_create(
        name='load_balancer_arn',
        defaults={
            "label": 'AWS Load Balancer ARN',
            "type": 'STR',
            'show_as_attribute': True,
            "description": "Used by the HA Architecture's AWS HA Load Balancer"
        }
    )
    CustomField.objects.get_or_create(
        name='load_balancer_dns',
        defaults={
            "label": 'AWS Load Balancer DNS',
            "type": 'URL',
            'show_as_attribute': True,
            "description": "Used by the HA Architecture's AWS HA Load Balancer blueprint"
        }
    )
    CustomField.objects.get_or_create(
        name='target_group_arn',
        defaults={
            "label": 'Target Group ARN',
            "type": 'STR',
            'show_as_attribute': False,
            "description": "Used by the HA Architecture"
        }
    )
    CustomField.objects.get_or_create(
        name='acm_certificate_arn',
        defaults={
            "label": 'ACM Certificate ARN',
            "type": 'STR',
            'show_as_attribute': True,
            "description": "Used by the HA Architecture"
        }
    )
    CustomField.objects.get_or_create(
        name='ha_load_balancer_dns',
        defaults={
            "label": 'Load Balancer Endpoint',
            "type": 'URL',
            'show_as_attribute': True,
            "description": "Used by the HA Architecture"
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


def get_boto3_ec2_client(**kwargs):
    rh = kwargs.get('resource_handler')
    region = kwargs.get('region', None)
    wrapper = rh.get_api_wrapper()
    return wrapper.get_boto3_client('ec2', rh.serviceaccount, rh.servicepasswd, region)


def generate_options_for_use_existing_acm_certificate(**kwargs):
    return [
        ('', '-- Select Choice --'),
        ('Yes', 'Yes'),
        ('No', 'No'),
    ]


def generate_options_for_acm_certificate_arn(control_value=None, **kwargs): 
    parent_bp = get_parent_bp(current_bp=kwargs.get('blueprint'))
    options = [("", "-- Select ACM Certificate --")]
    rh_id = None
    
    if control_value == 'Yes':
        cf_dict = parent_bp.get_cf_values_as_dict() if parent_bp else {}
        if 'global_ha_architecture_rh_id' in cf_dict:
            rh_id = cf_dict['global_ha_architecture_rh_id']
        if 'global_ha_architecture_locations' in cf_dict:
            raw_list = cf_dict['global_ha_architecture_locations'].split(",")
            region = raw_list[0].split("(")[-1].replace(")", "")
            
        if rh_id:
            rh = AWSHandler.objects.get(id=rh_id)
            acm_client = boto3.client(
                'acm', region_name=region,
                aws_access_key_id=rh.serviceaccount,
                aws_secret_access_key=rh.servicepasswd
            )
            response = acm_client.list_certificates()
            if len(response['CertificateSummaryList']) != 0:
                for certificate in response['CertificateSummaryList']:
                    options.append(
                        (certificate['CertificateArn'], f"{certificate['DomainName']}:-{certificate['CertificateArn']}")
                    )
            else:
                options.append(("NA", "No ACM certificate available in this region"))
        else:
            options.append(("", "--Select Instance Locations First from Parent Blueprint--"))
    elif control_value == 'No':
        options = [("NA", "--Create new ACM Certificate--")]
        
    return options


def run(job, *args, **kwargs):
    resource = kwargs.get('resource')
    get_or_create_custom_fields()
    
    use_existing_acm_certificate = '{{use_existing_acm_certificate}}'
    acm_certificate_arn = '{{acm_certificate_arn}}'
    base_name = "HA"
    
    if resource.parent_resource_id:
        parent_resource = Resource.objects.get(id=resource.parent_resource_id)
        base_name = parent_resource.base_name
        aws_ha_region = parent_resource.aws_region_ha
        hosted_zone_id = parent_resource.hosted_zone_id
        route53_rh_id = parent_resource.aws_rh_id_for_hosted_zone
        route53_rh = AWSHandler.objects.get(id=route53_rh_id)
        rh = AWSHandler.objects.get(id=parent_resource.aws_rh_id)
        vpc_subnet_sg_dict = ast.literal_eval(parent_resource.vpc_subnet_structure[-1])
        subnet_id_list = [subnet[0] for subnet in vpc_subnet_sg_dict[aws_ha_region]['Subnet']]
        instance_locations_list = parent_resource.aws_zone_region_list_ha[1].split(",")
        
        set_progress('VPC details retrieved as {}'.format(vpc_subnet_sg_dict))
    
    route53_wrapper = route53_rh.get_api_wrapper()
    route53_client = route53_wrapper.get_boto3_client('route53', route53_rh.serviceaccount, route53_rh.servicepasswd, None)
    wrapper = rh.get_api_wrapper()
    acm_client = wrapper.get_boto3_client('acm', rh.serviceaccount, rh.servicepasswd, aws_ha_region)
    
    response = route53_client.get_hosted_zone(Id=hosted_zone_id)
    domain_name = response['HostedZone']['Name'].rstrip(".")
    
    if use_existing_acm_certificate == 'Yes' and acm_certificate_arn != "NA":
        acm_certificate_arn = acm_certificate_arn
    else:
        set_progress(f"Creating New ACM Certificate in region {aws_ha_region}")
        response = acm_client.request_certificate(
            DomainName=f"*.{domain_name}",
            ValidationMethod='DNS',
        )
        acm_certificate_arn = response['CertificateArn']
        
        set_progress("Waiting for ACM to generate DNS CNAME validation records...")
        cname_ready = False
        for _ in range(12):
            cert_check = acm_client.describe_certificate(CertificateArn=acm_certificate_arn)
            validation_opts = cert_check['Certificate'].get('DomainValidationOptions', [])
            if validation_opts and 'ResourceRecord' in validation_opts[0]:
                cname_ready = True
                break
            time.sleep(5)

        if not cname_ready:
            return "FAILURE", "Timed out waiting for ACM to generate DNS validation CNAME record.", ""
        
    records = route53_client.list_resource_record_sets(HostedZoneId=hosted_zone_id)
    cname_record_list = [row for row in records['ResourceRecordSets'] if row['Type'] == 'CNAME']
    cname_record = {"Name": [cname['Name'] for cname in cname_record_list]} if len(cname_record_list) != 0 else {"Name": "NA"}
    
    is_cname_record_added_in_hosted_zone = False
    cert = acm_client.describe_certificate(CertificateArn=acm_certificate_arn)
    
    for cname_records_in_ACM in cert['Certificate']['DomainValidationOptions']:
        if cname_records_in_ACM['ResourceRecord']['Name'] in cname_record['Name']:
            set_progress(f"CNAME record already exists in Hosted Zone {domain_name}")
            is_cname_record_added_in_hosted_zone = True
            break
            
    if not is_cname_record_added_in_hosted_zone:
        for record_details in cert['Certificate']['DomainValidationOptions']:
            batch = {
                'Comment': 'Created by CloudBolt Job ID: {}'.format(job.id),
                'Changes': [
                    {
                        'Action': "CREATE",
                        'ResourceRecordSet': {
                            'ResourceRecords': [{'Value': record_details['ResourceRecord']['Value']}],
                            'Name': record_details['ResourceRecord']['Name'],
                            'Type': record_details['ResourceRecord']['Type'],
                            'TTL': 300
                        }
                    },
                ]
            }
            route53_client.change_resource_record_sets(HostedZoneId=hosted_zone_id, ChangeBatch=batch)
        set_progress(f"CNAME record added in Hosted Zone {domain_name}")

    region = aws_ha_region
    client = get_boto3_ec2_client(resource_handler=rh, region=region)
    vpc_id = vpc_subnet_sg_dict[region]['VPC'][0]
    resp_ig = client.describe_internet_gateways()
    is_internet_gateway_required = True
    
    for attachment in resp_ig['InternetGateways']:
        for conn in attachment['Attachments']:
            if conn['VpcId'] == vpc_id:
                is_internet_gateway_required = False
                
    ec2_resource = boto3.resource(
        service_name='ec2', region_name=region,
        aws_access_key_id=rh.serviceaccount, aws_secret_access_key=rh.servicepasswd
    )
    vpc_obj = ec2_resource.Vpc(vpc_id)
    
    if is_internet_gateway_required:
        set_progress(f"Creating internet gateway for VPC {vpc_id}")
        resp_ig = client.create_internet_gateway()
        ig_id = resp_ig['InternetGateway']['InternetGatewayId']
        resp_vpc_ig = vpc_obj.attach_internet_gateway(InternetGatewayId=ig_id)
        for rt in vpc_obj.route_tables.all():
            route_table = ec2_resource.RouteTable(rt.id)
            route = route_table.create_route(DestinationCidrBlock='0.0.0.0/0', GatewayId=ig_id)

    SecGrpID = vpc_subnet_sg_dict[region]['VPC'][-1]
        
    elbv_client = wrapper.get_boto3_client('elbv2', rh.serviceaccount, rh.servicepasswd, region)
    
    load_balancer_name = f'LoadBalancer-{base_name}'
    load_balancer_name = "".join([alphabet for alphabet in load_balancer_name if alphabet.isalnum() or alphabet == "-"])
    set_progress(f"Creating load balancer '{load_balancer_name}' for region {region}")
    
    resp_alb = elbv_client.create_load_balancer(
        Name=load_balancer_name,
        Subnets=subnet_id_list,
        SecurityGroups=[SecGrpID],
        Scheme='internet-facing',
        Type='application',
        IpAddressType='ipv4',
    )
    load_balancer_arn = resp_alb['LoadBalancers'][0]['LoadBalancerArn']
    load_balancer_name = resp_alb['LoadBalancers'][0]['LoadBalancerName']
    lb_dns_name = resp_alb['LoadBalancers'][0]['DNSName']

    tg_name = f'TG-{base_name}'
    set_progress(f"Creating target group '{tg_name}' for region '{region}'")
    tg_name = "".join([alphabet for alphabet in tg_name if alphabet.isalnum() or alphabet == "-"])
    resp_tg = elbv_client.create_target_group(Name=tg_name, Port=443, Protocol='HTTPS', VpcId=vpc_id, Matcher={'HttpCode': "200,302"})
    target_group_arn = resp_tg['TargetGroups'][0]['TargetGroupArn']
    
    if resource.parent_resource_id:
        parent_resource.vpc_subnet_structure = ("VPC Subnet Instance Structure details", vpc_subnet_sg_dict)
        parent_resource.ha_load_balancer_name = load_balancer_name
        parent_resource.target_group_arn = target_group_arn
        parent_resource.ha_load_balancer_dns = resource.load_balancer_dns
        parent_resource.ha_load_balancer_arn = load_balancer_arn
        parent_resource.ha_acm_certificate_arn = acm_certificate_arn
        parent_resource.save()
    
    retry_attempt = 0
    max_retries = 90
    sleep_interval = 10
    
    acm_cert_details = acm_client.describe_certificate(CertificateArn=acm_certificate_arn) 
    is_acm_certificate_status_not_issued = True
    
    if acm_cert_details['Certificate']['Status'] == "ISSUED":
        is_acm_certificate_status_not_issued = False
    elif acm_cert_details['Certificate']['Status'] == "PENDING_VALIDATION":
        set_progress("ACM Certificate is PENDING_VALIDATION. Waiting for Route53 DNS validation to propagate...")
        time.sleep(10)
        
        while is_acm_certificate_status_not_issued and retry_attempt < max_retries:
            retry_attempt += 1
            acm_cert_details = acm_client.describe_certificate(CertificateArn=acm_certificate_arn)
            cert_status = acm_cert_details['Certificate']['Status']
            
            if cert_status == "ISSUED":
                is_acm_certificate_status_not_issued = False
                set_progress(f"ACM Certificate successfully ISSUED on attempt {retry_attempt}!")
            elif cert_status == "FAILED":
                set_progress("ACM Certificate validation FAILED on AWS side.")
                break
            else:
                set_progress(
                    f"Waiting for ACM certificate status to become 'ISSUED' (Current status: '{cert_status}')... "
                    f"attempt ({retry_attempt}/{max_retries})"
                )
                time.sleep(sleep_interval)
    
    if is_acm_certificate_status_not_issued:
        return "FAILURE", "ACM Certificate validation timed out or failed. Kindly check if FQDN is working properly and try again", ""    
    
    resp_listener = elbv_client.create_listener(
        DefaultActions=[
            {
                'TargetGroupArn': target_group_arn,
                'Type': 'forward',
            },
        ],
        LoadBalancerArn=load_balancer_arn,
        Port=443,
        Protocol='HTTPS',
        Certificates=[
            {
                'CertificateArn': acm_certificate_arn,
            },
        ],
    )
    
    resp_listener = elbv_client.create_listener(
        DefaultActions=[
            {
                'Type': 'redirect',
                'RedirectConfig': {
                    'Protocol': 'HTTPS',
                    'Port': '443',
                    'Host': '#{host}',
                    'Path': '/#{path}',
                    'Query': '#{query}',
                    'StatusCode': 'HTTP_302'
                },
            },
        ],
        LoadBalancerArn=load_balancer_arn,
        Port=80,
        Protocol='HTTP',
    )
    
    lb_resp = elbv_client.describe_load_balancers(LoadBalancerArns=[load_balancer_arn])
    load_balancer_canonical_hosted_zone_id = lb_resp['LoadBalancers'][0]['CanonicalHostedZoneId']
    load_balancer_dns_name = lb_resp['LoadBalancers'][0]['DNSName']
    
    resource.load_balancer_name = load_balancer_name
    resource.load_balancer_arn = load_balancer_arn
    resource.load_balancer_dns = lb_dns_name
    resource.acm_certificate_arn = acm_certificate_arn
    resource.save()
    
    if resource.parent_resource_id:
        batch = {
            'Changes': [
                {
                    'Action': "CREATE",
                    'ResourceRecordSet': {
                        'AliasTarget': {
                            'HostedZoneId': load_balancer_canonical_hosted_zone_id,
                            'DNSName': load_balancer_dns_name,
                            'EvaluateTargetHealth': True
                        },
                        'Name': f"{base_name}.{domain_name}",
                        'Type': 'A',
                    }
                },
            ],
            'Comment': 'Created by CloudBolt Job ID: {}'.format(job.id),
        }
        
        route53_client.change_resource_record_sets(HostedZoneId=hosted_zone_id, ChangeBatch=batch)
        set_progress(f"Load balancer '{load_balancer_name}' DNS 'A' record successfully added in hosted zone")

    return "SUCCESS", f"Application Load Balancer {load_balancer_name} created successfully", ""