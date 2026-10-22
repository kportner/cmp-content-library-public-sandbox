import { LoaderClass, DATA_BACKUP_HOURS, numberFormatter,
         DIMENSION_DATA, AWS_SERVICE_MAP, MONTH_NAMES, SERVER_PARTS,
         POTENTIAL_SAVINGS, lockModal, unlockModal } from './common.js';

var dailyState = true;
var monthlyState = false;
var startDate;
var totalDays;
var endDate;
var datesArray;
var csvStr;
var pdfData = [];
var pageGap = 0;
var stdTypeList = ["CIS", "PCI", "NIST", "HIPAA", "AWSWA"];
var loaderObjCompliance = new LoaderClass('compliance-tab');

const COLOR_SCHEME = {
  CIS: "#002F52",
  PCI: "#25AA41",
  NIST: "#818C96",
  HIPAA: "#18A0FD",
  AWSWA: "#FFBF2F"
}
const RESOURCE_HANDLER = {
  handlerId: $('#handler_details_compliance').data('handlerid'),
  handlerType: $('#handler_details_compliance').data('handler'),
  handlerCurrency: $('#handler_details_compliance').data('acurrency'),
  handlerNormalId : String($('#handler_details_compliance').data('normalid')),
  normalAdapterId: $('#handler_details_compliance').data('normaladapter'),
  validation: $('#handler_details_compliance').data('validation'),
}

$(document).ajaxStop(function() {
  loaderObjCompliance.hide();
});

$(document).ready(function () {
  if (RESOURCE_HANDLER.validation == "True") {
    bootstrap.Modal.getOrCreateInstance($('#compliance-tab .errorMessageModal')[0]).hide();
    $('#complianceTabDiv').css('filter', 'none');
    $('#compliance-tab .go-to-admin').addClass('d-none');
    $('#compliance-tab .go-to-rh').addClass('d-none');
    $('#compliance-tab .no-data').addClass('d-none');
    $('#compliance-tab .overviewButton').addClass('d-none');
    unlockModal();
    loaderObjCompliance.display();
    getComplianceOverview();
    getComplianceReport();

    $('.btn-toggle').click(function() {
      $(this).find('.btn').toggleClass('active');
      if ($(this).find('.btn-primary').length>0) {
        $(this).find('.btn').toggleClass('btn-primary');
      }
      $(this).find('.btn').toggleClass('btn-default');

      if ($($('.dailyMonthlyState button[class~="active"]')[0]).text() == 'Daily') {
        dailyState = true;
        monthlyState = false;
      } else {
        dailyState = false;
        monthlyState = true;
      }
      getSecurityTrends();
    });

    $(window).resize(function(){
      var chart = $('#line-chart-div').highcharts();
      var w = $('#line-chart-div').closest(".wrapper").width()
      chart.setSize(w,290,false);

      var chart = $('#area-chart-div').highcharts();
      var w = $('#area-chart-div').closest(".wrapper").width()
      chart.setSize(w,290,false);
    });
  }
  else {
    bootstrap.Modal.getOrCreateInstance($('#compliance-tab .errorMessageModal')[0]).show();
    lockModal();
    $('#complianceTabDiv').css('filter', 'blur(10px)');
    $('#compliance-tab .go-to-admin').removeClass('d-none');
    $('#compliance-tab .go-to-rh').addClass('d-none');
    $('#compliance-tab .no-data').addClass('d-none');
  }
});

function setDateRange() {
  let start = moment().subtract(30, 'days');
  let end = moment().subtract(1, 'days')

  function formatDate(start, end) {
    startDate = start.format('MMMM D, YYYY');
    endDate = end.format('MMMM D, YYYY');
    $('div[name="daterange-compliance"] span').val(start.format('MM/DD/YYYY') + '-' + end.format('MM/DD/YYYY'));
    $('div[name="daterange-compliance"] span').html(start.format('MM/DD/YYYY') + '-' + end.format('MM/DD/YYYY'));
    totalDays = end.diff(start, 'days');
    let singular = (totalDays > 1) ? "days" : "day"
    $('.total-days').text(`${totalDays + 1} ${singular}`);
    getSecurityTrends();
  }
  $('div[name="daterange-compliance"]').daterangepicker({
    startDate: start,
    endDate: end,
    ranges: {
    'Yesterday': [moment().subtract(1, 'days'), moment().subtract(1, 'days')],
    'Last 7 Days': [moment().subtract(7, 'days'), moment().subtract(1, 'days')],
    'Last 30 Days': [moment().subtract(30, 'days'), moment().subtract(1, 'days')],
    'Current Month': [moment().startOf('month'), moment().subtract(1, 'days')],
    'Previous Month': [moment().subtract(1, 'month').startOf('month'), moment().subtract(1, 'month').endOf('month')],
    'Current Quarter': [getQuarter("current").quarteStart, getQuarter("current").quarterEnd],
    'Previous Quarter': [getQuarter("previous").quarteStart, getQuarter("previous").quarterEnd],
    }
  }, formatDate)
  formatDate(start, end)
}

function getQuarter(id) {
  let d = new Date();
  let quarter = Math.floor((d.getMonth() / 3));
  let firstDate = "";
  let endDate = "";

  switch (id) {
    case "current":
    firstDate = new Date(d.getFullYear(), quarter * 3, 1);
    endDate = new Date(firstDate.getFullYear(), firstDate.getMonth() + 3, 0);
    break;
    case "previous":
    firstDate = new Date(d.getFullYear(), quarter * 3 - 3, 1);
    endDate = new Date(firstDate.getFullYear(), firstDate.getMonth() + 3, 0);
    break;
  }

  return {
    quarteStart: firstDate,
    quarterEnd: endDate
  };
}

function plotLineChart(series, labels, chartType) {
  $('#line-chart-div').highcharts({
    chart: {
      type: chartType,
      height: 235
    },
    title: {
      text: null
    },
    legend: { enabled: true },
    xAxis: {
      categories: labels,
      labels: {
        enabled: true,
        overflow: "allow",
        rotation: -90,
        y: 10,
        formatter: function () {
          if (dailyState) {
            return this.value.slice(-2)
                    + this.value.slice(4, 8)
                    + this.value.slice(2, 4);
          } else {
            return this.value
          }
        }
      }
    },
    yAxis: {},
    tooltip: {
      shared: false,
    },
    credits: {
      enabled: false
    },
    plotOptions: {
      spline: {
        marker: {
          enabled: true,
          radius: 2
        },
        lineWidth: 3
      },
      series: {
        pointWidth: 45
      },
    },
    series: series,
  });
}

function plotAreaChart(series, labels, chartType) {
  $('#area-chart-div').highcharts({
    chart: {
      type: chartType,
      height: 235
    },
    title: {
      text: 'Overall Compliance'
    },
    legend: { enabled: true },
    xAxis: {
      categories: labels,
      labels: {
        enabled: true,
        overflow: "allow",
        rotation: -90,
        y: 10,
        formatter: function () {
          if (dailyState) {
            return this.value.slice(-2)
                  + this.value.slice(4, 8)
                  + this.value.slice(2, 4);
          } else {
            return this.value
          }
        }
      }
    },
    yAxis: {},
    tooltip: {
      shared: false,
    },
    credits: {
      enabled: false
    },
    plotOptions: {
      areaspline: {
        fillOpacity: 0.6,
        marker: {
          enabled: false,
        }
      },
      series: {
        pointWidth: 45
      }
    },
    series: series,
  });
}

function getSecurityTrends() {
  loaderObjCompliance.display();
  // datesArray = getDatesBetweenDates(new Date(startDate), new Date(endDate));
  let json_data = {
    daily: dailyState,
    monthly: monthlyState,
    provider_account_id: String(RESOURCE_HANDLER.handlerNormalId),
    rh_id: RESOURCE_HANDLER.handlerId,
  }

  if(RESOURCE_HANDLER.handlerType == "AWS"){
    json_data.compliance_report = {
      start_date: startDate,
      end_date: endDate,
    }
  }
  else if(RESOURCE_HANDLER.handlerType == "Azure"){
    json_data.start_date = startDate;
    json_data.end_date = endDate;
  }
  $.ajax({
    url: "/xui/kumo/api/get_security_trends/",
    type: 'POST',
    dataType: 'json',
    data: {
      body: JSON.stringify(json_data)
    },
    success: function (response) {
      // console.log(response);
      let favouriteDates = [];
      let favouriteTypeWise = [];
      let overallDates = [];
      let overallTypeWise = [];
      let tempOverallDataArray = [];
      let chartType = "";

      if (Object.keys(response.result).includes("message")) {
        bootstrap.Modal.getOrCreateInstance($('#compliance-tab .errorMessageModal')[0]).show();
        $('#complianceTabDiv').css('filter', 'blur(10px)');
        $('#compliance-tab .no-normal-comp').removeClass('d-none');
      }
      else {
        if (Object.keys(response.result).length != 0) {
          bootstrap.Modal.getOrCreateInstance($('#compliance-tab .errorMessageModal')[0]).hide();
          $('#complianceTabDiv').css('filter', 'none');
          $('#compliance-tab .no-normal-comp').addClass('d-none');

          response.result.favourite.chart_data.categories[0].category.forEach(dates => {
            favouriteDates.push(dates.label);
          });

          response.result.favourite.chart_data.dataset.forEach((chartData, index) => {
            let tempDataArray = [];
            chartData.data.forEach(types => {
              tempDataArray.push(types.value);
            });

            favouriteTypeWise.push({
              name: chartData.seriesname,
              color: COLOR_SCHEME[chartData.seriesname],
              data: tempDataArray
            });
          });

          response.result.overall.chart_data.forEach(chartData => {
            overallDates.push(chartData.label);
            tempOverallDataArray.push(chartData.value);
          });

          overallTypeWise.push({
            name: "Average",
            color: "#2F701F",
            data: tempOverallDataArray
          });
        }

        if ((totalDays + 1) == 1) {
          chartType = "column";
        } else {
          chartType = "spline";
        }
        plotLineChart(favouriteTypeWise, favouriteDates, chartType);

        if ((totalDays + 1) == 1) {
          chartType = "column";
        } else {
          chartType = "areaspline";
        }
        plotAreaChart(overallTypeWise, overallDates, chartType);
      }
      loaderObjCompliance.hide();
    },
    error: function (xhr) {
      // alert("An error occured: " + xhr.status + " " + xhr.statusText);
      // loaderObjCompliance.hide();
    },
    timeout: 30000
  });
}

function getComplianceReport() {
  // loaderObjCompliance.display();
  // datesArray = getDatesBetweenDates(new Date(startDate), new Date(endDate));
  $.ajax({
    url: "/xui/kumo/api/get_compliance_report/",
    type: 'GET',
    dataType: 'json',
    data: {
      body: JSON.stringify({
        provider_account_id: String(RESOURCE_HANDLER.handlerNormalId),
        rh_id: RESOURCE_HANDLER.handlerId,
      })
    },
    success: function (response) {
      // console.log(response);
      if (Object.keys(response.result).includes("message")) {
        bootstrap.Modal.getOrCreateInstance($('#compliance-tab .errorMessageModal')[0]).show();
        $('#complianceTabDiv').css('filter', 'blur(10px)');
        $('#compliance-tab .no-normal-comp').removeClass('d-none');
      }
      else {
        bootstrap.Modal.getOrCreateInstance($('#compliance-tab .errorMessageModal')[0]).hide();
        $('#complianceTabDiv').css('filter', 'none');
        $('#compliance-tab .no-normal-comp').addClass('d-none');

        response.result.forEach(types => {
          // $(`#${types.standard_type.toLowerCase()}_count`).text(`${types.threat_count} / ${types.total_count}`);
          $(`#${types.standard_type.toLowerCase()}_prog`).text(`${types.compliance_progress}%`);
          $(`#${types.standard_type.toLowerCase()}_prog_nc`).text(`${100 - types.compliance_progress}%`);
          $(`#${types.standard_type.toLowerCase()}_prog_percent`).css('width', `${types.compliance_progress}%`);
          // $(`#${types.standard_type.toLowerCase()}_prog_percent`).text(`${types.threat_count}`);
          $(`#${types.standard_type.toLowerCase()}_prog_percent_nc`).css('width', `${100 - types.compliance_progress}%`);
          // $(`#${types.standard_type.toLowerCase()}_prog_percent_nc`).text(`${types.total_count - types.threat_count}`);
        });
        // loaderObjCompliance.hide();
      }
      setDateRange();
    },
    error: function (xhr) {
      setDateRange();
      // alert("An error occured: " + xhr.status + " " + xhr.statusText);
      // loaderObjCompliance.hide();
    },
    timeout: 30000
  });
}

function getComplianceOverview() {
  // loaderObjCompliance.display();
  // datesArray = getDatesBetweenDates(new Date(startDate), new Date(endDate));
  var stdVersionMap = {};
  if(RESOURCE_HANDLER.handlerType == "AWS"){
    stdVersionMap["CIS"] = "1.2.0"
    stdVersionMap["PCI"] = "3.2.1"
    stdVersionMap["NIST"] = "1.1.0"
    stdVersionMap["HIPAA"] = "5010"
    stdVersionMap["AWSWA"] = "1.0.0"
  }
  else if(RESOURCE_HANDLER.handlerType == "Azure"){
    stdVersionMap["CIS"] = "1.3.0"
    stdVersionMap["PCI"] = "3.2.1"
    stdVersionMap["NIST"] = "Rev.5"
    stdVersionMap["HIPAA"] = "9.2"
    stdVersionMap["AWSWA"] = "1.0.0"
  }

  stdTypeList.forEach(types => {
    $.ajax({
      url: "/xui/kumo/api/get_compliance_overview/",
      type: 'GET',
      dataType: 'json',
      data: {
        body: JSON.stringify({
          standard_type: types,
          standard_version: stdVersionMap[types],
          provider_account_id: String(RESOURCE_HANDLER.handlerNormalId),
          rh_id: RESOURCE_HANDLER.handlerId,
        })
      },
      success: function (response) {
        // console.log(response);
        if (Object.keys(response.result).includes("message")) {
          bootstrap.Modal.getOrCreateInstance($('#compliance-tab .errorMessageModal')[0]).show();
          $('#complianceTabDiv').css('filter', 'blur(10px)');
          $('#compliance-tab .no-normal-comp').removeClass('d-none');
        }
        else {
          bootstrap.Modal.getOrCreateInstance($('#compliance-tab .errorMessageModal')[0]).hide();
          $('#complianceTabDiv').css('filter', 'none');
          $('#compliance-tab .no-normal-comp').addClass('d-none');

          let responseChartData = {};
          response.result.chart_data.forEach(element => {
            responseChartData[element.label] = element.value;
          });
          $(`#${types.toLowerCase()}_very_high`).text(responseChartData["very high"] !== undefined ? responseChartData["very high"] : responseChartData["very high"]);
          $(`#${types.toLowerCase()}_high`).text(responseChartData["high"] !== undefined ? responseChartData["high"] : responseChartData["High"]);
          $(`#${types.toLowerCase()}_medium`).text(responseChartData["medium"] !== undefined ? responseChartData["medium"] : responseChartData["Medium"]);
          $(`#${types.toLowerCase()}_low`).text(responseChartData["low"] !== undefined ? responseChartData["low"] : responseChartData["Low"]);
          $(`#${types.toLowerCase()}_by_type`).text(`${response.result.fail_count_by_type}`);
          $(`#${types.toLowerCase()}_by_resource`).text(`${response.result.fail_count_by_resource}`);
          // loaderObjCompliance.hide();
        }
      },
      error: function (xhr) {
        // alert("An error occured: " + xhr.status + " " + xhr.statusText);
        // loaderObjCompliance.hide();
      },
      timeout: 30000
    });
  });
}