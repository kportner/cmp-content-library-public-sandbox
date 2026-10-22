#!/usr/bin/env python

"""
This action should be run as a recurring job,
"""
from datetime import datetime
from jobs.models import Job
from orders.models import Order
from common.methods import set_progress
from utilities.exceptions import CloudBoltException
from django.db.models import Q

# Cancel job using order id
def cancel_job_from_order_id(order_id):
    set_progress("Canceling all jobs of order id #{}".format(order_id))
    try:
        order_object = Order.objects.get(id=order_id)
        for job in order_object.list_of_jobs():
            set_progress(job)
            job.status = 'CANCELED'
            job.save()
    except Exception as e:
        set_progress(e)
        raise CloudBoltException(e)

# Cancel job using job id
def cancel_job_from_job_id(job_id):
    set_progress("Canceling job using job id #{}".format(job_id))
    try:
        job_obj = Job.objects.get(id=job_id)
        set_progress(job_obj)
        job_obj.status = 'CANCELED'
        job_obj.save()
    except Exception as e:
        set_progress(e)
        raise CloudBoltException(e)

def run(job, *args, **kwargs):

    today = datetime.today()

    order_id = "{{order_id}}"
    job_id  = "{{job_id}}"

    if order_id and job_id:
        cancel_job_from_job_id(job_id)
    elif order_id:
        cancel_job_from_order_id(order_id)
    elif job_id:
        cancel_job_from_job_id(job_id)
    else:
        # if user has not given order id and job id
        set_progress("Canceling Job running longer than 24 hrs")
        for job_obj in Job.objects.filter(Q (status='RUNNING') | Q (status='TO_CANCEL')):
            try:
                if job_obj:
                    hours_running = (today - job.start_date).total_seconds() / 3600
                    if hours_running >= 24:
                        set_progress(job_obj)
                        job_obj.status = 'CANCELED'
                        job_obj.save()
                else:
                    set_progress("Not Found any running or To_CANCEL Job")
                     
            except Exception as e:
                set_progress(e)
                raise CloudBoltException(e)

    return ("SUCCESS", "", "")     

if __name__ == "__main__":
    run()