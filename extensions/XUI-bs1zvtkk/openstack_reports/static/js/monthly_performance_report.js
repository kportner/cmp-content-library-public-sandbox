import { LoaderClass } from './common.js';
import { createHeader, createFooter } from './pdf_common.js';

function formatMB(mb, decimals = 2) {
  if (mb === "" || mb ==0){
    return {
      'value': 0,
      'unit': 'MB'
    }
  }

  const k = 1024
  const dm = decimals < 0 ? 0 : decimals
  const sizes = ['MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']

  const i = Math.floor(Math.log(mb) / Math.log(k))

  // return `${parseFloat((mb / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`
  return {
    'value': `${parseFloat((mb / Math.pow(k, i)).toFixed(dm))}`,
    'unit': `${sizes[i]}`
  }
}

function formatBytes(bytes, decimals = 2) {
  if (bytes === "" || bytes ==0){
    return {
      'value': 0,
      'unit': 'B'
    }
  }

  const k = 1024
  const dm = decimals < 0 ? 0 : decimals
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']

  const i = Math.floor(Math.log(bytes) / Math.log(k))

  // return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`
  return {
    'value': `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))}`,
    'unit': `${sizes[i]}`
  }
}

function formatTime(nanoseconds) {
  // Convert nanoseconds to seconds
  let seconds = nanoseconds / 1e9;
  let conversion_value = seconds
  let conversion_unit = "Sec"
  // Check if it exceeds 60 seconds
  if (seconds >= 60) {
      // Convert seconds to minutes
      let minutes = seconds / 60;

      // Check if it exceeds 60 minutes
      if (minutes >= 60) {
          // Convert minutes to hours
          let hours = minutes / 60;
          conversion_value = hours.toFixed(2);
          conversion_unit = "Hrs"
      } else {
          conversion_value = minutes.toFixed(2);
          conversion_unit = "Min"
          // return minutes.toFixed(2) + " Minutes";
      }
  } else {
      conversion_value = seconds.toFixed(2);
      conversion_unit = "Sec"
      // return seconds.toFixed(2) + " Seconds";
  }
  return {
    "value": conversion_value,
    "unit": conversion_unit
  }
}

var pageGap = 0;

var loaderObjServer = new LoaderClass('chart-group');
var cpuStatChartOpts = {
  chart: {
    zoomType: 'xy'
  },
  title: {
    text: ''
  },
  xAxis: {
    type: 'datetime',
    tickPixelInterval: 150
  },
  yAxis: { // Primary yAxis
    labels: {
      formatter: function() {
        var current_value = this.value;
        return `${formatTime(current_value).value} ${formatTime(current_value).unit}`
      },
      style: {
        color: '#335b83'
      }
    },
    title: {
      text: 'CPU Usage (Time Used)',
      style: {
        color: '#335b83'
      }
    }
  },
  credits: {
    enabled: false
  },
  exporting: {
    enabled: false
  }
};

var memStatChartOpts = {
  chart: {
    zoomType: 'xy'
  },
  title: {
    text: ''
  },
  xAxis: {
    type: 'datetime',
    tickPixelInterval: 150
  },
  yAxis: { // Primary yAxis
    labels: {
      formatter: function() {
        var current_value = this.value;
        return `${formatMB(current_value).value} ${formatMB(current_value).unit}`
      },
      style: {
        color: '#335b83'
      }
    },
    title: {
      text: gettext('Memory Usage'),
      style: {
        color: '#335b83'
      }
    }
  },
  credits: {
    enabled: false
  },
  exporting: {
    enabled: false
  }
};

var netStatChartOpts = {
  chart: {
    zoomType: 'xy'
  },
  title: {
    text: ''
  },
  xAxis: {
    type: 'datetime',
    tickPixelInterval: 150
  },
  yAxis: { // Primary yAxis
    labels: {
      formatter: function() {
        var current_value = this.value;
        return `${formatBytes(current_value).value} ${formatBytes(current_value).unit}`
      },
      style: {
        color: '#335b83'
      }
    },
    title: {
      text: 'Network Usage',
      style: {
        color: '#335b83'
      }
    }
  },
  credits: {
    enabled: false
  },
  exporting: {
    enabled: false
  }
};

function seriesData(startTime, interval, pointValues, serverEventsSorted, isPercentage) {
  var data = [];
  var intervalInMS = interval * 1000;
  var x, i, k, point, event;
  // dict of server history events on a particular x value (time), used
  // by tooltips
  var eventAtTime = {};

  if (isPercentage) {
     var denominator = 100.0;
  } else {
     var denominator = 1.0;
  }
  for (i = 0; i < pointValues.length; i++) {
     x = startTime + (i * intervalInMS);
     let pointVal = pointValues[i] ? pointValues[i] : 0
     point = {
        x: x,
        //Previously, Math.round() was rounding values less than 0.5% down to 0%.
        y: isPercentage ? parseFloat((parseFloatNull(pointVal, denominator) * 100).toFixed(2)) : 
        parseFloat((parseFloatNull(pointVal, denominator)).toFixed(2)),
        marker: {
           enabled: false
        }
     };

     // go through the events that haven't been processed yet and
     // add them to the series if they happened before this point.
     for (k = 0; k < serverEventsSorted.length; k++) {
        event = serverEventsSorted[k];
        if (point.x > event.epoch_ms) {
           //point.color = '#393';
           point.marker = {
              enabled: true,
              fillColor: '#393',
              lineColor: '#060',
              radius: 10,
              symbol: 'diamond'
              //symbol: url('event-type-icon.png')
           };

           // data used by tooltip
           eventAtTime[point.x] = event;

           // remove it from the list of events
           serverEventsSorted.splice(k, 1);
        }
     }

     data.push(point);
  }

  return {
     data: data,
     eventAtTime: eventAtTime,
     average: avg(_.map(data, 'y'))
  };
}

function getServerStatTooltip(series, percentage, is_cpu_stat, is_memory_stat) {
  return {
    formatter: function () {
      var s = '<b>' + Highcharts.dateFormat('%b %e %Y at %H:%M:%S', this.x) + '</b>';

      _.forEach(this.points, function (point) {
        if (percentage) {
          s += '<br/>' + point.series.name + ': <b>' + point.y + '% </b>';
        }
        else if(is_cpu_stat && !is_memory_stat) {
          s += '<br/>' + point.series.name + ': <b>' + `${formatTime(point.y).value} ${formatTime(point.y).unit}` + '</b>';
        }
        else if(!is_cpu_stat && is_memory_stat) {
          s += '<br/>' + point.series.name + ': <b>' + `${formatMB(point.y).value} ${formatMB(point.y).unit}` + '</b>';
        }
        else {
          s += '<br/>' + point.series.name + ': <b>' + `${formatBytes(point.y).value} ${formatBytes(point.y).unit}` + '</b>';
        }

      });

      if (series.eventAtTime[this.x] !== undefined) {
        var e = series.eventAtTime[this.x];
        // add server event info
        s += '<div class="chart-tip event-tip">';
        s += 'Event: <b>' + e.type + '</b><br/>';
        s += 'Owner: <b>' + e.owner_html + '</b><br/>';
        s += 'Job: <b>' + e.job_html + '</b><br/>';
        s += '<p>' + e.message + '</p>';
        s += '</div>';
      }

      return s;
    },
    useHTML: true,
    shared: true
  };
}

function avg(values) {
  var filtered_values,
    total_value,
    n = values.length;
  if (n === 0) {
    return 0;
  }

  // The `.without` function will remove the `null`'s that we used to replace
  // empty values with in our `values` array, allowing us to correctly
  // calculate the average.
  filtered_values = _.without(values, null);
  total_value = sum(filtered_values);
  if (total_value == 0 || filtered_values.length == 0) {
    return 0;
  }
  return total_value / filtered_values.length;
}

function sum(values) {
  var filtered_values, n, i, s = 0;

  filtered_values = _.without(values, null);
  n = filtered_values.length;

  if (n == 0) {
    return 0;
  }

  for (i = 0; i < n; i++) {
    s += filtered_values[i];
  }
  return s;
}

function parseFloatNull(value, denominator) {
  var nan_values = ['', 'null'];
  if (nan_values.includes(value)) {
    return null;
  }

  return parseFloat(value) / denominator;
}

function plotCPUutilization(startTime, interval, cpuUsageValues, serverEvents, options) {
  if (cpuUsageValues === undefined) {
    cpuUsageValues = [];
  }

  // array of event objects sorted chronologically
  var serverEventsSorted = _.sortBy(serverEvents, 'epoch_ms');
  var series = seriesData(startTime, interval, cpuUsageValues, serverEventsSorted, false);

  $('#cpu-container').highcharts(_.merge({
    subtitle: {
      text: gettext('CPU Stats')
    },
    series: [
      {
        name: 'Usage',
        color: '#335b83',
        type: 'line',
        data: series.data
      }, {
        name: 'Average',
        color: '#4a9de4',
        type: 'spline',
        marker: { enabled: false },
        data: (function () {
          var i,
            points = [],
            n = series.data.length;
          for (i = 0; i < n; i++) {
            points.push({
              x: series.data[i].x,
              y: Math.round(series.average * 100) / 100
            });
          }
          return points;
        }())
      }],
    tooltip: getServerStatTooltip(series, false, true, false)
  }, options));
}

function plotMemoryutilization(startTime, interval, memUsageValues, serverEvents, options) {
  if (memUsageValues === undefined) {
    memUsageValues = [];
  }

  // array of event objects sorted chronologically
  var serverEventsSorted = _.sortBy(serverEvents, 'epoch_ms');
  var series = seriesData(startTime, interval, memUsageValues, serverEventsSorted, false);

  $('#mem-container').highcharts(_.merge({
    subtitle: {
      text: gettext('Memory Stats')
    },
    series: [
      {
        name: 'Usage',
        color: '#335b83',
        type: 'line',
        data: series.data
      }, {
        name: 'Average',
        color: '#4a9de4',
        type: 'spline',
        marker: { enabled: false },
        data: (function () {
          var i,
            points = [],
            n = series.data.length;
          for (i = 0; i < n; i++) {
            points.push({
              x: series.data[i].x,
              y: Math.round(series.average * 100) / 100
            });
          }
          return points;
        }())
      }],
    tooltip: getServerStatTooltip(series, false, false, true)
  }, options));
}

function plotNetworIncomingkutilization(startTime, interval, netUsageValues, serverEvents, options) {
  if (netUsageValues === undefined) {
    netUsageValues = [];
  }

  // array of event objects sorted chronologically
  var serverEventsSorted = _.sortBy(serverEvents, 'epoch_ms');
  var series = seriesData(startTime, interval, netUsageValues, serverEventsSorted, false);

  $('#net-container').highcharts(_.merge({
    subtitle: {
      text: gettext('Network Incoming Stats')
    },
    series: [
      {
        name: 'Throughput',
        color: '#335b83',
        type: 'line',
        data: series.data
      }, {
        name: 'Average',
        color: '#4a9de4',
        type: 'spline',
        marker: { enabled: false },
        data: (function () {
          var i,
            points = [],
            n = series.data.length;
          for (i = 0; i < n; i++) {
            points.push({
              x: series.data[i].x,
              y: Math.round(series.average * 100) / 100
            });
          }
          return points;
        }())
      }],
    tooltip: getServerStatTooltip(series, false, false, false)
  }, options));
}

function plotNetworOutgoingkutilization(startTime, interval, netUsageValues, serverEvents, options) {
  if (netUsageValues === undefined) {
    netUsageValues = [];
  }

  // array of event objects sorted chronologically
  var serverEventsSorted = _.sortBy(serverEvents, 'epoch_ms');
  var series = seriesData(startTime, interval, netUsageValues, serverEventsSorted, false);

  $('#net-outgoing-container').highcharts(_.merge({
    subtitle: {
      text: gettext('Network Outgoing Stats')
    },
    series: [
      {
        name: 'Throughput',
        color: '#335b83',
        type: 'line',
        data: series.data
      }, {
        name: 'Average',
        color: '#4a9de4',
        type: 'spline',
        marker: { enabled: false },
        data: (function () {
          var i,
            points = [],
            n = series.data.length;
          for (i = 0; i < n; i++) {
            points.push({
              x: series.data[i].x,
              y: Math.round(series.average * 100) / 100
            });
          }
          return points;
        }())
      }],
    tooltip: getServerStatTooltip(series, false, false, false)
  }, options));
}

function plotGraphs(start_date, end_date, vm_id, url) {
  if(vm_id == null || vm_id == undefined || vm_id == ""){
    $("#error-message").css({ "display": "block" }).text("No VM details found");
    $("#pdf-report").prop('disabled', true);
    return false;
  }
  else if (Date.parse(start_date) > Date.parse(end_date)) {
    $("#error-message").css({ "display": "block" }).text("Please select proper date range, end date is before start date.");
    $("#pdf-report").prop('disabled', true);
    return false;
  }
  else if (Date.parse(start_date) == Date.parse(end_date)) {
    $("#error-message").css({ "display": "block" }).text("Please select proper date range, start date and end date can't be same.");
    $("#pdf-report").prop('disabled', true);
    return false;
  }
  else if (Date.parse(end_date) > (Date.parse(start_date) + 2592000000)) {
    $("#error-message").css({ "display": "block" }).text("Please select proper date range, end date can't be greater than 30 days from the start date.");
    $("#pdf-report").prop('disabled', true);
    return false;
  }
  else {
    $("#error-message").css({ "display": "none" });
    loaderObjServer.display();
    $.ajax({
      url: url,
      type: 'POST',
      dataType: 'json',
      data: {
        body: JSON.stringify({
          start_date: start_date,
          end_date: end_date,
          vm_id: vm_id,
        })
      },
      success: function (response) {
        if (response['message_status'] == true) {
          let start_datetime = new Date(start_date);
          let startTime = Date.UTC(start_datetime.getUTCFullYear(), start_datetime.getUTCMonth(), start_datetime.getUTCDate(), start_datetime.getUTCHours(), start_datetime.getUTCMinutes(), start_datetime.getUTCSeconds());
          var serverEvents = _.filter([], function (event) {
            return event.epoch_ms >= chartSettings.startTime;
          });
          $("#chart-group").show();
          plotCPUutilization(startTime, response['interval'], response['result'][0].cpu_usage_values, serverEvents, cpuStatChartOpts)
          plotMemoryutilization(startTime, response['interval'], response['result'][0].mem_usage_values, serverEvents, memStatChartOpts)
          plotNetworIncomingkutilization(startTime, response['interval'], response['result'][0].net_usage_values, serverEvents, netStatChartOpts)
          plotNetworOutgoingkutilization(startTime, response['interval'], response['result'][0].net_outgoing_usage_values, serverEvents, netStatChartOpts)
        }
        $("#pdf-report").prop('disabled', false);
        loaderObjServer.hide();
      },
      error: function (xhr) {
        loaderObjServer.hide();
        alert("An error occured: " + xhr.status + " " + xhr.statusText);
      }
    });
  }
}

function downloadPDF(start_date, end_date, server_name) {
  if (Date.parse(start_date) > Date.parse(end_date)) {
    $("#error-message").css({ "display": "block" }).text("Please select proper date range, end date is before start date.");
    return false;
  }
  else if (Date.parse(start_date) == Date.parse(end_date)) {
    $("#error-message").css({ "display": "block" }).text("Please select proper date range, start date and end date can't be same.");
    return false;
  }
  else if (Date.parse(end_date) > (Date.parse(start_date) + 2592000000)) {
    $("#error-message").css({ "display": "block" }).text("Please select proper date range, end date can't be greater than 30 days from the start date.");
    return false;
  }
  else {
    var doc = new jsPDF();

    var img1, img2, img3, img4;
    pageGap = 10;
    doc.setFont('helvetica');
    doc.setFontType('bold');
    createHeader(doc);
    doc.setFontSize(12);
    doc.text(pageGap, pageGap + 25, 'Filters:');
    doc.setFontSize(10);
    doc.text(pageGap + 10, pageGap + 30, `Selected VM: ${server_name}`)
    doc.text(pageGap + 10, pageGap + 35, `Start Date: ${start_date}`)
    doc.text(pageGap + 10, pageGap + 40, `End Date: ${end_date}`)

    doc.setFontSize(12);
    doc.text(pageGap, pageGap + 50, 'Monthly VM Basic Inventory:');
    doc.setFontSize(10);
    doc.autoTable({ html: '#basic-vm-inventory', startY: 70, margin: { right: 10, left: 10 }, pageBreak: 'auto' });


    var cpuDivHeight = $('#cpu-container').height();
    var cpuDivWidth = $('#cpu-container').width();
    var cpuRatio = cpuDivHeight / cpuDivWidth;

    var memDivHeight = $('#mem-container').height();
    var memDivWidth = $('#mem-container').width();
    var memRatio = memDivHeight / memDivWidth;

    var netDivHeight = $('#net-container').height();
    var netDivWidth = $('#net-container').width();
    var netRatio = netDivHeight / netDivWidth;

    var outDivHeight = $('#net-outgoing-container').height();
    var outDivWidth = $('#net-outgoing-container').width();
    var outRatio = outDivHeight / outDivWidth;

    var width;
    var height;
    //  This is for "Monthly VM CPU utilization" 
    html2canvas(document.getElementById("cpu-container"), {
      height: cpuDivHeight,
      width: cpuDivWidth,
    }).then(function (canvas) {

      img1 = canvas.toDataURL("image/png")
      width = doc.internal.pageSize.width;
      height = doc.internal.pageSize.height;
      height = cpuRatio * width;
      pageGap = 10;
      doc.addPage();
      createHeader(doc);
      doc.setFont('helvetica');
      doc.setFontType('bold');
      doc.setFontSize(12);
      doc.text(pageGap, pageGap + 25, 'Monthly VM CPU utilization:');
      doc.addImage(img1, 'PNG', 10, pageGap + 30, width - 20, height - 10);
    });

    //  This is for "Monthly VM Memory utilization"
    html2canvas(document.getElementById("mem-container"), {
      height: memDivHeight,
      width: memDivWidth,
    }).then(function (canvas) {

      img2 = canvas.toDataURL("image/png")
      width = doc.internal.pageSize.width;
      height = doc.internal.pageSize.height;
      height = memRatio * width;
      doc.setFont('helvetica');
      doc.setFontType('bold');
      doc.setFontSize(12);
      doc.text(pageGap, pageGap + 150, 'Monthly VM Memory utilization:');
      doc.addImage(img2, 'PNG', 10, pageGap + 150, width - 20, height - 10);

    });

    //  This is for "Monthly VM Network Incoming utilization"
    html2canvas(document.getElementById("net-container"), {
      height: netDivHeight,
      width: netDivWidth,
    }).then(function (canvas) {

      img3 = canvas.toDataURL("image/png")
      width = doc.internal.pageSize.width;
      height = doc.internal.pageSize.height;
      height = netRatio * width;
      pageGap = 10;
      doc.addPage();
      doc.setFont('helvetica');
      doc.setFontType('bold');
      doc.setFontSize(12);
      createHeader(doc);
      doc.text(pageGap, pageGap + 25, 'Monthly VM Network Incoming utilization:');
      doc.addImage(img3, 'PNG', 10, pageGap + 30, width - 20, height - 10);
    });

    //  This is for "Monthly VM Network Outgoing utilization"
    html2canvas(document.getElementById("net-outgoing-container"), {
      height: outDivHeight,
      width: outDivWidth,
    }).then(function (canvas) {

      img4 = canvas.toDataURL("image/png")
      width = doc.internal.pageSize.width;
      height = doc.internal.pageSize.height;
      height = outRatio * width;
      doc.setFont('helvetica');
      doc.setFontType('bold');
      doc.setFontSize(12);
      doc.text(pageGap, pageGap + 150, 'Monthly VM Network Outgoing utilization:');
      doc.addImage(img4, 'PNG', 10, pageGap + 150, width - 20, height - 10);


      let report_name = "Openstack VM Usage Report".split(' ').join('_') + moment().format('_DDMMYYYYhhmmss');
      createFooter(doc);
      doc.save(report_name + '.pdf');

    });
  }
}

$(document).ready(function () {
  // loaderObjServer.display();
  //  loaderObjServer.hide();
  $('#basic-vm-inventory').DataTable();

  var start_date = $("#start_date").val();
  var end_date = $("#end_date").val();
  var vm_id = $("#select-vm").val();
  var url = $("#plot-graph").data('url');
  plotGraphs(start_date, end_date, vm_id, url)

  $("#plot-graph").on("click", function () {
    start_date = $("#start_date").val();
    end_date = $("#end_date").val();
    vm_id = $("#select-vm").val();
    url = $(this).data('url');
    $("#chart-group").hide();
    plotGraphs(start_date, end_date, vm_id, url);
  });

  $(document).on('click', '#pdf-report', function (e) {
    start_date = $("#start_date").val();
    end_date = $("#end_date").val();
    var server_name = $("#select-vm").find(':selected').data("name");
    downloadPDF(start_date, end_date, server_name);
  });

});