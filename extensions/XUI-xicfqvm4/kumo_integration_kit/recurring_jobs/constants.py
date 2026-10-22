EFFICIENCY_PAYLOAD_AWS = {
    "adapter_id": "",
    "adapter_ids": "",
    "region_id": "",
    "service_type": "",
    "lifecycle": "",
    "count": "true",
    "tags": "[]",
    "tag_operator": "OR",
    "vcenter_id": "",
    "public_snapshot": "false",
    "sort_by": "days_old",
    "sort": "ASC",
    "service_adviser_klass": "ServiceAdviser::AWS",
    "rh_id": "",
    "provider_account_id": ""
}

EFFICIENCY_PAYLOAD_AZURE = {
    "adapter_id": "",
    "adapter_ids": "",
    "region_id": "",
    "service_type": "",
    "lifecycle": "",
    "count": "true",
    "tags": "[]",
    "tag_operator": "OR",
    "vcenter_id": "",
    "public_snapshot": "false",
    "sort_by": "days_old",
    "sort": "ASC",
    "service_adviser_klass": "ServiceAdviser::Azure",
    "rh_id": "",
    "provider_account_id": ""
}

EFFICIENCY_PAYLOAD_GCP = {
    "adapter_id": "",
    "adapter_ids": "",
    "region_id": "",
    "service_type": "",
    "lifecycle": "",
    "count": "true",
    "tags": "[]",
    "tag_operator": "OR",
    "vcenter_id": "",
    "public_snapshot": "false",
    "sort_by": "days_old",
    "sort": "ASC",
    "service_adviser_klass": "ServiceAdviser::GCP",
    "provider_account_id": ""
}

SPEND_PAYLOAD_AWS = {
   "report":{
      "daily":True,
      "date_range":{
         "start_date":"",
         "end_date":""
      },
      "tags":{

      },
      "type":"cost_report",
      "account":[

      ],
      "service":[

      ],
      "region":[

      ],
      "usage_type":[

      ],
      "operation":[

      ],
      "monthly":False,
      "multi_series": "service",
      "select_metric":"unblended",
      "product_family":[

      ],
      "is_upfront_reservation_charges":True,
      "is_support_charges":True,
      "is_other_subscription_charges":True,
      "is_credit": True,
      "is_margin": True,
      "is_discount": True,
      "is_edp": True,
      "is_refund": True,
      "is_tax_charge": True,
      "is_tax_refund": True,
      "rh_id":9,
      "dimensions":[
         "date"
      ],
      "metrics":[
         "unblended"
      ],
      "provider_account_id":""
   },
   "total_days":30,
   "total_months":2
}

SPEND_PAYLOAD_AZURE = {
   "report":{
      "daily": True,
      "monthly": False,
      "group_by":"date_range",
      "resource_group":[

      ],
      "date_range":{
         "start_date":"",
         "end_date":""
      },
      "consumed_service":[

      ],
      "service_name":[

      ],
      "service_tier":[

      ],
      "resource_name":[

      ],
      "tags":{

      },
      "location":[

      ],
      "type":"azure_cost_report",
      "provider":"Azure",
      "multi_series": "service_name",
      "tab":"custom",
      "subscription":[

      ],
      "dimensions":[
         "date"
      ],
      "metrics":[
         "cost"
      ],
      "select_metric":"cost",
      "rh_id": "",
      "provider_account_id": ""
   },
   "total_days":30,
   "total_months":2
}

SPEND_PAYLOAD_GCP = {
   "report":{
      "daily": True,
      "monthly": False,
      "group_by":"date_range",
      "date_range":{
         "start_date":"",
         "end_date":""
      },
      "sku":[

      ],
      "service":[

      ],
      "location":[

      ],
      "project":[

      ],
      "tags":{

      },
      "type":"gcp_cost_report",
      "provider":"GCP",
      "multi_series": "service",
      "tab":"custom",
      "is_invoice": True,
      "is_partner_discount": True,
      "is_reseller_margin": True,
      "dimensions":[
         "date"
      ],
      "metrics":[
         "cost"
      ],
      "select_metric":"cost",
      "rh_id": "",
      "provider_account_id":[]
   },
   "total_days":30,
   "total_months":2
}

RIGHT_SIZED_PAYLOAD = {
    "noloa`der": "",
    "adapter_id": "",
    "service_type": "rds_snapshot",
    "service_adviser_klass": "ServiceAdviser::AWS",
    "rh_id": "",
    "sort_by": "provider_created_at",
    "provider_account_id": "",
    "region_id": "",
    "lifecycle": "",
    "sort": "ASC",
    "public_snapshot": "false",
    "tags": "[]",
    "per_page": 1000,
    "page": 1
}

IGNORED_SERVICES_PAYLOAD = {
    "noloader": "",
    "adapter_id": "",
    "service_type": "",
    "service_adviser_klass": "ServiceAdviser::AWS",
    "rh_id": "",
    "sort_by": "ASC",
    "provider_account_id": "",
    "region_id": "",
    "lifecycle": "",
    "sort": "ASC",
    "public_snapshot": "false",
    "tags": "[]",
    "per_page": 1000,
    "page": 1,
    "count": "true"
}
