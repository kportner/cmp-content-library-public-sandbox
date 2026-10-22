from accounts.models import Group,UserProfile
from resources.models import ResourceType
from reportengines.internal.export_utils import GroupCostDetails
from common.methods import set_progress
import datetime,os,time
from orders.models import CustomFieldValue
from infrastructure.models import CustomField


def run(job, *args, **kwargs):

    target_group = int("{{target_group}}" or 0)
    run_period = int("{{run_period}}" or 30)  # Default is set to Last Month if user dont set default
    start = "{{start_date}}"
    end = "{{end_date}}"
    profile = job.owner
    final_target_group = None if target_group==0 else Group.objects.filter(id=target_group)

    all_groups = Group.objects_for_profile(profile) if profile else Group.objects.all()
    groups = final_target_group if final_target_group else all_groups
    set_progress(f"Report target group :- {groups.first().name if final_target_group else 'All Groups'}")
    
    kwargs_dict = dict()
    if run_period == 0:
        # Use Custom dates provided by user
        if start and end:
            start_date = datetime.datetime.fromisoformat(start).replace(tzinfo=None)
            end_date = datetime.datetime.fromisoformat(end).replace(tzinfo=None)
            set_progress("Fetching report for custom dates entered by user")
        else:
            kwargs_dict["custome_dates_without_user_input"] = "Start and End dates not provided"
            start_date, end_date = report_period(**kwargs_dict)
    else:
        if run_period == 30:
            kwargs_dict["last_month"] = "Last Month"
        elif run_period == 1:
            kwargs_dict["current_month"] = "Current Month"
        else:
            kwargs_dict["days_back"] = run_period
        start_date, end_date = report_period(**kwargs_dict)
    
    if (end_date - start_date).total_seconds() < 0:
        return "FAILURE", "End date can not be earlier than Start Date",""
        
    set_progress(f"Report start date is {start_date}")
    set_progress(f"Report end date is {end_date}")

    for group in groups:
        group_id_str = "group_{}".format(group.id)
        report = GroupCostDetails(group, profile, start_date, end_date)
        set_progress(f"Searching cache data for '{group.name}' if available")
        file_path = report.get_group_cost_report_filename("data", group_id_str=group_id_str)
        is_cache_file_already_exists = os.path.exists(file_path)
        if is_cache_file_already_exists:
            set_progress(f"skipping caching because cached group cost data for '{group.name}'' is already exists")
        else:
            set_progress(f"No cache data found, calculating group cost data for '{group.name}'")
            g_data = report._calculate_group_cost_data(group.id)
            report.cache_group_cost_report(g_data, group_id_str)
            set_progress(f"Caching group cost data for {group.name} is completed")

    return "SUCCESS","Succcessfully cached the cost data for intended group or groups","" #"Job Successfull",

def get_owner_profile(**kwargs):
    profile = kwargs.get("profile",None)
    if not profile:
        profile = kwargs.get("recipient",None)

    return profile
    
def generate_options_for_target_group(field,*args, **kwargs):
    profile = get_owner_profile(**kwargs)
    if profile:
        groups = Group.objects_for_profile(profile)
    else:
        groups = Group.objects.all()
    options = [(0,"All Groups")]
    options.extend([(g.id,g.name) for g in groups])

    return {
        'options': options,
    }

def report_period(**kwargs):
    """
    Return 2-tuple of DateTime for period start and end dates.
    """
    str_format="%Y-%m-%d"
    force_past=True
    keys = list(kwargs.keys())

    dt = datetime.datetime
    now = dt.now()
    yesterday = now - datetime.timedelta(days=1)

    if "days_back" in kwargs.keys():
        # Make the period N days ago to end of yesterday
        set_progress(f"Fetching report for a period of last {kwargs.get('days_back',0)} days")
        days_back = int(kwargs["days_back"])
        start_date = now - datetime.timedelta(days=days_back)
        end_date = dt(yesterday.year, yesterday.month, yesterday.day, 23, 59, 59)
    elif "last_month" in kwargs.keys():
        # Return dates for the previous calendar month
        set_progress(f"Fetching report for a {kwargs.get(keys[0],'Unknown Period')}")
        start_date, end_date = last_month_info()
    elif "current_month" in kwargs.keys():
        # Return dates for the current calendar month
        set_progress(f"Fetching report for a {kwargs.get(keys[0],'Unknown Period')}")
        start_date, end_date = current_month_info()
    else:
        start_date = kwargs.get("start_date", None)
        end_date = kwargs.get("end_date", None)

        if start_date:
            start_date = mkDateTime(start_date, strFormat=str_format)
        if end_date:
            end_date = mkDateTime(end_date, strFormat=str_format)

        # can't run cost report for future dates
        if force_past:
            if end_date and end_date > yesterday:
                end_date = yesterday

        # the default period will be the whole previous month
        if not start_date or not end_date or end_date < start_date:
            first_day_of_last_month, last_day_of_last_month = last_month_info()
            if not start_date:
                start_date = first_day_of_last_month
            if not end_date:
                end_date = last_day_of_last_month
            set_progress("Fetching report for a Last Month as start and end dates are not provided by user")

    end_date = end_date.replace(hour=23, minute=59, second=59)

    return start_date, end_date

def current_month_info():
    today = datetime.datetime.today()
    first_day_of_current_month = today.replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    yesterday = today - datetime.timedelta(days=1)

    last_day_of_current_month = yesterday.replace(
        hour=23, minute=59, second=59, microsecond=0,
    )
    return (first_day_of_current_month, last_day_of_current_month)
    
def last_month_info():
    """
    Return a tuple with the (first day of last month, last day of last month)

    These are returned as time objects, with the time of the first item set to
    00:00:00 and the time of the second set to 23:59:59, so that if the caller
    is doing some math to calculate the total # of hours in the month, they
    will count the full first & last days.
    """
    today = datetime.datetime.today()
    last_months_year = today.year
    last_month = today.month - 1
    if last_month == 0:
        last_month = 12
        last_months_year = last_months_year - 1
    first_day_of_last_month = today.replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
        month=last_month,
        year=last_months_year,
    )

    # to get the last day of last month, start from the first day of this month
    # and subtract one day
    last_day_of_last_month = today.replace(
        hour=23, minute=59, second=59, microsecond=0, day=1
    ) - datetime.timedelta(days=1)
    return (first_day_of_last_month, last_day_of_last_month)


def generate_options_for_run_period(field, **kwargs):

    options = [
        (0, 'Custom Dates'),
        (1,'Current Month'),
        (30, 'Last Month'),
        (7, 'Last One week'),
        (14, 'Last Two weeks'),
        (21, 'Last Three weeks'),
    ]

    return options