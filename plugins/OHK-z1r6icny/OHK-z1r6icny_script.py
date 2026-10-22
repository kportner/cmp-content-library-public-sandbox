from common.methods import set_progress
from infrastructure.models import Server, CustomField, ServerSnapshot
from resourcehandlers.openstack.models import OpenStackHandler
from history.models import ServerHistory
from infrastructure.templatetags import infrastructure_tags as infra_tags
from django.utils.html import escape
from datetime import datetime
from utilities.mail import email
from emailtemplates.models import EmailTemplate
from utilities.templatetags import helper_tags
from costs.utils import is_rates_feature_enabled


# This class will return the VM Details
class VMDetails(object):
    def __init__(self, resource=None, server=None):
        self.resource = resource
        self.server = server

    def get_hardware_details(self):
        set_progress("Fetching hardware details")
        data = {
            "cpu": self.server.cpu_cnt,
            "memory": CustomField(name="mem_size").render_value(self.server.mem_size),
            "disk": self.server.disk_size
        }
        return data


    def get_configuration_details(self):
        set_progress("Fetching configuration details")
        data = {
            "status": self.server.status,
            "hostname": self.server.hostname,
            "ip_address": self.server.ip,
            "date_added": format_date(self.server.add_date)
        }
        if is_rates_feature_enabled():
            data["rate"] = self.server.rate_display_with_tooltip
        return data


    def get_openstack_details(self):
        set_progress("Fetching openstack details")
        openstack_details = self.server.resource_handler.cast().tech_specific_server_details(self.server)
        snapshots = ServerSnapshot.objects.filter(server=self.server)
        snapshot_data = []
        for obj in snapshots:
            json_data = {}
            json_data["date_created"] = format_date(obj.date_created)
            json_data["name"] = obj.name
            json_data["description"] = obj.description
            json_data["identifier"] = obj.identifier
            snapshot_data.append(json_data)
            
        if not openstack_details:
            set_progress(
                f"No OpenStack details found for server: {self.server.hostname} "
                f"(ID: {self.server.id})"
            )
            return {
                "tenant": None,
                "availability_zone": None,
                "tags": [],
                "snapshots": snapshot_data,
            }
        data = {
            "tenant": openstack_details.location,
            "availability_zone": openstack_details.availability_zone,
            "tags": openstack_details.tags,
            "snapshots": snapshot_data
        }
        return data


    def get_disk_details(self):
        set_progress("Fetching disk details")
        server_disks = self.server.disks.all()
        data = []
        for disk in server_disks:
            json_data = {}
            json_data["id"]= disk.id
            json_data["uuid"]= disk.uuid
            json_data["disk_size"]= disk.disk_size
            json_data["name"]= disk.name
            data.append(json_data)
        return data


    def get_network_details(self):
        set_progress("Fetching network details")
        nics = self.server.nics.all()
        data = []
        for nic in nics:
            json_data = {}
            json_data["ip"] = nic.ip
            json_data["private_ip"] = nic.private_ip
            json_data["mac"] = nic.mac
            json_data["netwrok"] = nic.network_id
            data.append(json_data)
        return data


    def get_power_schedule_details(self):
        set_progress("Fetching power schedule details")
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        data = []
        
        power_schedule = getattr(self.server, "power_schedule", None) or []

        for schedule in power_schedule:
            json_data = {} 
            json_data["on_day"] = days[schedule['on_day']]
            json_data["on_hour"] = schedule['on_hour']
            json_data["off_day"] = days[schedule['off_day']]
            json_data["off_hour"] = schedule['off_hour']
            json_data["timezone"] = schedule['timezone']
            data.append(json_data)
        return data


    def get_history_details(self):
        set_progress("Fetching power schedule details")
        history = ServerHistory.objects.filter(server=self.server)
        data = []
        for event in history:
            json_data = {}
            json_data["date"] = format_date(event.action_time)
            json_data["type"] = infra_tags.show_event_type_verbose(event)
            json_data["owner"] = (
                    escape(event.owner.user.get_full_name())
                    if event.owner and event.owner.user
                    else "N/A"
                )
            json_data["event"] = event.event_message
            data.append(json_data)
        return data


# This function will convert the date and time format
def format_date(date):
    date_time_str = date.strftime("%Y-%m-%d %H:%M:%S")
    return date_time_str


# This function will get or create Email Template object
def get_or_create_email_template(response_data):
    name = "VMDetails Notification"
    subject = "VMDetails Notification"
    if not EmailTemplate.objects.filter(name="VMDetails Notification").exists():
        template_obj = EmailTemplate.objects.create(name=name, subject=subject)
    else:
        template_obj = EmailTemplate.objects.get(name=name, subject=subject)

    body = ""
    for server in response_data:
        disk_counter = 1
        network_counter = 1
        schedule_counter = 1
        history_counter = 1
        snapshot_counter = 1
        body+="<li><strong>Name: "+str(server['configuration']['hostname'])+"</strong><br><ul>"
        body+="<li><strong>Hardware:</strong></li><ul><li>CPUs: "+str(server['hardware']['cpu'])+" </li><li>Memory: "+str(server['hardware']['memory'])+" </li><li>Disk: "+str(server['hardware']['disk'])+" </li></ul>"
        body+="<li><strong>Configuration:</strong></li><ul><li>Status: "+str(server['configuration']['status'])+" </li><li>Hostname: "+str(server['configuration']['hostname'])+" </li><li>IP Address: "+str(server['configuration']['ip_address'])+" </li><li>Date Added: "+str(server['configuration']['date_added'])+" </li>"
        if server['configuration'].get('rate'):
            body+="<li>Rate: "+str(server['configuration']['rate'])+" </li></ul>"
        else:
            body+="</ul>"
        body+="<li><strong>Others:</strong></li><ul><li>Tenant: "+str(server['openstack']['tenant'] or "")+" </li><li>Availability Zone: "+str(server['openstack']['availability_zone'])+" </li><li>Tags: "+str(server['openstack']['tags'])+" </li>"
        body+="<li>Snapshots:</li><ul>"
        # Forloop for snapshots
        if server['openstack']['snapshots']:
            for obj in server['openstack']['snapshots']:
                body+="<li> Snapshot-"+str(snapshot_counter)+" <ul><li>Date Created: "+str(obj['date_created'])+" </li><li>Name: "+str(obj['name'])+" </li><li>Description: "+str(obj['description'])+" </li><li>Identifier: "+str(obj['identifier'])+" </li></ul></li>"
                snapshot_counter+=1
        else:
            body+="<li>No snapshots available</li>"
        body+="</ul>"
        body+="</ul>"
        body+="<li><strong>Disk:</strong></li><ul>"
        # Forloop for disk
        if server['disk']:
            for obj in server['disk']:
                body+="<li> Disk-"+str(disk_counter)+" <ul><li>ID: "+str(obj['id'])+" </li><li>Name: "+str(obj['name'])+" </li><li>Disk Size: "+str(obj['disk_size'])+" </li><li>UUID: "+str(obj['uuid'])+" </li></ul></li>"
                disk_counter+=1
        else:
            body+="<li>No disks available</li>"
        body+="</ul>"
        body+="<li><strong>Networks:</strong></li><ul>"
        # Forloop for networks
        if server['network']:
            for obj in server['network']:
                body+="<li>NIC-"+str(network_counter)+" </li><ul><li>IP: "+str(obj['ip'])+" </li><li>Private IP: "+str(obj['private_ip'])+" </li><li>MAC: "+str(obj['mac'])+" </li><li>Netwrok: "+str(obj['netwrok'])+" </li></ul>"
                network_counter+=1
        else:
            body+="<li>No network available</li>"
        body+="</ul>"
        body+="<li><strong>Power Schedule:</strong></li><ul>"
        # Forloop for power schedule
        if server['power_schedule']:
            for obj in server['power_schedule']:
                body+="<li>Schedule-"+str(schedule_counter)+" </li><ul><li>ON Day: "+str(obj['on_day'])+" </li><li>ON Hour: "+str(obj['on_hour'])+" </li><li>OFF Day: "+str(obj['off_day'])+" </li><li>OFF Hour: "+str(obj['off_hour'])+" </li><li>Timezone: "+str(obj['timezone'])+" </li></ul>"
                schedule_counter+=1
        else:
            body+="<li>No power schedule available</li>"
        body+="</ul>"
        body+="<li><strong>History:</strong></li><ul>"
        # Forloop for history
        if server['history']:
            for obj in server['history']:
                body+="<li>History-"+str(history_counter)+" </li><ul><li>Date: "+str(obj['date'])+" </li><li>Type: "+str(obj['type'])+" </li><li>Owner: "+str(obj['owner'])+" </li><li>Event: "+str(obj['event'])+"</li></ul>"
                history_counter+=1
        else:
            body+="<li>No history available</li>"
        body+="</ul></ul>"
        body+="<p>____________________________________________________________________________</p>"
        body+="</li>"
    template_obj.body = body
    template_obj.save()
    return template_obj


def run(job, *args, **kwargs):
    set_progress("Recurring Job for notification initiated")
    response_data = []
    resources = OpenStackHandler.objects.all()
    for resource in resources:
        servers = resource.server_set.all().exclude(status="HISTORICAL")
        for server in servers:
            
            if server.status not in ["ACTIVE", "POWERON", "POWEROFF"]:
                set_progress(f"Skipping server '{server.hostname}' with status '{server.status}'.")
                continue
            
            json_data = {}
            
            vm_details = VMDetails(resource=resource, server=server)
            json_data['hardware'] = vm_details.get_hardware_details()
            json_data['configuration'] = vm_details.get_configuration_details()
            json_data['openstack'] = vm_details.get_openstack_details()
            json_data['disk'] = vm_details.get_disk_details()
            json_data['network'] = vm_details.get_network_details()
            json_data['power_schedule'] = vm_details.get_power_schedule_details()
            json_data['history'] = vm_details.get_history_details()
            response_data.append(json_data)
    template_obj = get_or_create_email_template(response_data)
    recipients=[] # This should be the list of emails
    email_context = dict(message=response_data)
    email(slug=template_obj.slug, recipients=recipients, context=email_context)

    if True:
        return "SUCCESS", "Sample output message", ""
    else:
        return "FAILURE", "Sample output message", "Sample error message, this is shown in red"
