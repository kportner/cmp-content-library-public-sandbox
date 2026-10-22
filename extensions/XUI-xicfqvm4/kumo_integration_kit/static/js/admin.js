
import { LoaderClass, DATA_BACKUP_HOURS, numberFormatter,
         MONTH_NAMES, sanitizeHtml, showAlert
} from './common.js';

var last_12_months_cc;
var add_new_counter = 0;
var preferredCurrency;
var loaderObjAdmin = new LoaderClass('admin-tab');
const RESOURCE_HANDLER = {
  handlerId: $('#handler_details_admin').data('handlerid'),
  handlerType: $('#handler_details_admin').data('handler')
}

function setDisabled($el, disabled) {
  $el.prop('disabled', disabled);
}

$(document).ready(function () {
  last_12_months_cc = setConvRateMonths();
  getCreds(get_rh_list);
  $(".hide-button").hide();
  $(".hide-button-edit").hide();
  $(".hide-button-cust").hide();
  $("#currency-conversion-new").hide();

  $(document).ajaxStop(function() {
    loaderObjAdmin.hide();
  });

  $(document).keydown(function(event) {
    if (event.keyCode == 27) {
      $('.btn-close').click();
    }
  });

  $(document).on('click', '.edit-conversion', function (e) {
    let clicked_id = this.id.substring(5,);
    if ($(`#cr-${clicked_id}`).hasClass('d-none')) {
      setDisabled($(`#source-${clicked_id}, #target-${clicked_id}`), false);
      $(`#cr-${clicked_id}`).removeClass('d-none');
      $(`#hide-button-edit-${clicked_id}`).removeClass('d-none');
      $(`.curr-conv-${clicked_id}`).prop('disabled', false);
    }
    else {
      setDisabled($(`#source-${clicked_id}, #target-${clicked_id}`), true);
      $(`#cr-${clicked_id}`).addClass('d-none');
      $(`#hide-button-edit-${clicked_id}`).addClass('d-none');
      $(`.curr-conv-${clicked_id}`).prop('disabled', true);
      $(`#update-currency-conv-${clicked_id}`).empty();
      $(`#cancel-edit-${clicked_id}`).text("Cancel Edit");
    }
  });

  $(document).on('change', '#cc-status', function (e) {
    loaderObjAdmin.display();
    $.ajax({
      url: "/xui/kumo/api/save_preferred_currency/",
      type: 'GET',
      dataType: 'json',
      data: {
        body: JSON.stringify({
          enable_currency_conversion: $("#cc-status").prop("checked"),
        })
      },
      success: function (response) {
        if (!$("#cc-status").prop("checked")) {
          // $(".currency-preference").addClass("d-none");
          $("#pref-curr").val("");
        }
        else {
          // $(".currency-preference").removeClass("d-none");
          $("#pref-curr").val("");
          $("#edit-pref-curr").click();
        }
      },
      error: function (xhr) {
        alert("An error occured: " + xhr.status + " " + xhr.statusText);
      },
      timeout: 30000
    });
  });

  $(document).on('submit', '#currencyConversionForm', function (e) {
    e.preventDefault();
    loaderObjAdmin.display();
    $.ajax({
      url: "/xui/kumo/api/save_preferred_currency/",
      type: 'GET',
      dataType: 'json',
      data: {
        body: JSON.stringify({
          // enable_currency_conversion: $("#cc-status").prop("checked"),
          default_currency: $("#pref-curr").val()
        })
      },
    success: function (response) {
        $("#save-pref-curr").parent().addClass("d-none");
        $("#pref-curr").val($("#pref-curr").val());
        $("#pref-curr").prop("disabled", true);
        get_rh_list(get_config);
      },
      error: function (xhr) {
        alert("An error occured: " + xhr.status + " " + xhr.statusText);
      },
      timeout: 30000
    });
  });

  $(document).on('click', '#edit-pref-curr', function (e) {
    $(this).next().removeClass("d-none");
    $("#pref-curr").prop("disabled", false);
  });

  $(document).on('click', '.cancel-save-pref-curr', function (e) {
    $(this).parent().addClass("d-none");
    $("#pref-curr").prop("disabled", true);
    $("#pref-curr").val(preferredCurrency);
  });

  $(document).on('click', '.delete-conversion', function (e) {
    $(this).next().removeClass("d-none");
  });

  $(document).on('click', '.not-sure-remove-cc', function (e) {
    $(this).parent().addClass("d-none");
  });

  $(document).on('click', '.sure-remove-cc', function (e) {
    loaderObjAdmin.display();
    let clicked_id = $(this).data("ccid");
    $.ajax({
      url: "/xui/kumo/api/all_currency_conv/",
      type: 'POST',
      dataType: 'json',
      data: {
        body: JSON.stringify({
          cc_id: clicked_id,
          call_type: "DELETE",
        })
      },
      success: function (response) {
        if (response.result == "nothing") {
          // $(`#block-${clicked_id}`).remove();
          get_rh_list(get_config);
        }
      },
      error: function (xhr) {
        alert("An error occured: " + xhr.status + " " + xhr.statusText);
      },
      timeout: 30000
    });
  });

  $(document).on('click', '.update-conversion', function (e) {
    $("#update-currency-error").css({"display": "none"});
    let clicked_id = this.id.substring(7,);
    let exchange_r = {};
    let invalid_value = false;
    let leading_zero = false;
    let trailing_dot = false;
    let cloud_provider_currency = $(`#source-${clicked_id}`).val();
    let default_currency = $(`#target-${clicked_id}`).val();
    if (cloud_provider_currency == default_currency){
      $("#update-currency-error").text("Preferred currency and Target currency could not be same. Please select different Target currency").css({"display": "inline-flex"});
      return false;
    }
    last_12_months_cc.forEach(month => {
      const d = new Date(month);
      let month_no = ((d.getMonth()+1) < 10) ? `0${d.getMonth()+1}` : d.getMonth()+1;
      let month_name = `${d.getFullYear()}-${month_no}`
      let month_rate = $(`#${clicked_id}-${month.slice(0,3)}`).val()
      if (month_rate[0] == '0') {
        leading_zero = true;
      }
      if(/^[0-9]\d*(\.\d+)?$/.test(month_rate) == false || parseFloat(month_rate) <= 0.0){
        if (month_rate.slice(-1) == ".") {
          trailing_dot = true;
        }
        else {
          invalid_value = true;
        }
      }
      exchange_r[month_name] = month_rate
    });
    if (invalid_value == true){
      $("#add-currency-error").text("Conversion value should be greater than 0 for all months.").css({"display": "inline-flex"});
      $("#update-currency-error").text("Conversion value should be greater than 0 for all months.").css({"display": "inline-flex"});

      return false;
    }
    if (leading_zero == true){
      $("#add-currency-error").text("Please remove the leading zero in conversion values.").css({"display": "inline-flex"});
      $("#update-currency-error").text("Please remove the leading zero in conversion values.").css({"display": "inline-flex"});

      return false;
    }
    if (trailing_dot == true){
      $("#add-currency-error").text("Please remove the trailing dot (.) from conversion values.").css({"display": "inline-flex"});
      $("#update-currency-error").text("Please remove the trailing dot (.) from conversion values.").css({"display": "inline-flex"});

      return false;
    }
    loaderObjAdmin.display();
    $.ajax({
      url: "/xui/kumo/api/all_currency_conv/",
      type: 'POST',
      dataType: 'json',
      data: {
        body: JSON.stringify({
          cloud_provider_currency: cloud_provider_currency,
          default_currency: default_currency,
          exchange_rates: exchange_r,
          cc_id: $(this).data("ccid"),
          call_type: "PATCH",
        })
      },
      success: function (response) {
        $(`#months-${clicked_id}`).empty();
        last_12_months_cc.forEach(month => {
          const d = new Date(month);
          let month_no = ((d.getMonth()+1) < 10) ? `0${d.getMonth()+1}` : d.getMonth()+1;
          let month_name = `${d.getFullYear()}-${month_no}`
          $(`#months-${clicked_id}`).append(`
            <div>
              <div><label class="form-label">${month}</label></div>
              <div><input type="text" min="0" class="curr-conv-${clicked_id}" id="${clicked_id}-${month.slice(0,3)}" style="width: 70%;" value="${response.result.currency_configuration.exchange_rates[month_name]}" disabled></div>
            </div>
          `)
          $(`#update-currency-conv-${clicked_id}`).text("Updated conversion rates successfully!");
          $(`#cancel-edit-${clicked_id}`).text("Done!");
        });
      },
      error: function (xhr) {
        alert("An error occured: " + xhr.status + " " + xhr.statusText);
      },
      timeout: 30000
    });
  });

  $(document).on('click', '.add-conversion', function (e) {
    $("#add-currency-error").css({"display": "none"});
    let clicked_id = this.id.substring(8,);
    let exchange_r = {};
    let cloud_provider_currency = $(`#source-new-${clicked_id}`).val();
    let default_currency = $(`#target-new-${clicked_id}`).val();
    let invalid_value = false;
    let leading_zero = false;
    let trailing_dot = false;
    if (cloud_provider_currency == default_currency){
      $("#add-currency-error").text("Preferred currency and Target currency could not be same. Please select different Target currency").css({"display": "inline-flex"});
      return false;
    }
    last_12_months_cc.forEach(month => {
      const d = new Date(month);
      let month_no = ((d.getMonth()+1) < 10) ? `0${d.getMonth()+1}` : d.getMonth()+1;
      let month_name = `${d.getFullYear()}-${month_no}`
      let month_rate = $(`#${clicked_id}-${month.slice(0,3)}`).val()
      if (month_rate[0] == '0') {
        leading_zero = true;
      }
      if(/^[0-9]\d*(\.\d+)?$/.test(month_rate) == false || parseFloat(month_rate) <= 0.0){
        if (month_rate.slice(-1) == ".") {
          trailing_dot = true;
        }
        else {
          invalid_value = true;
        }
      }
      exchange_r[month_name] = month_rate
    });
    if (invalid_value == true){
      $("#add-currency-error").text("Conversion value should be greater than 0 for all months.").css({"display": "inline-flex"});
      $("#update-currency-error").text("Conversion value should be greater than 0 for all months.").css({"display": "inline-flex"});
      return false;
    }
    if (leading_zero == true){
      $("#add-currency-error").text("Please remove the leading zero in conversion values.").css({"display": "inline-flex"});
      $("#update-currency-error").text("Please remove the leading zero in conversion values.").css({"display": "inline-flex"});

      return false;
    }
    if (trailing_dot == true){
      $("#add-currency-error").text("Please remove the trailing dot (.) from conversion values.").css({"display": "inline-flex"});
      $("#update-currency-error").text("Please remove the trailing dot (.) from conversion values.").css({"display": "inline-flex"});

      return false;
    }
    loaderObjAdmin.display();
    $.ajax({
      url: "/xui/kumo/api/all_currency_conv/",
      type: 'POST',
      dataType: 'json',
      data: {
        body: JSON.stringify({
          cloud_provider_currency: $(`#source-new-${clicked_id}`).val(),
          default_currency: $(`#target-new-${clicked_id}`).val(),
          provider: $(this).data("provider"),
          exchange_rates: exchange_r,
          call_type: "POST",
        })
      },
      success: function (response) {
        $(`#block-new-${clicked_id}`).remove();
        let currency_conversion = response.result.currency_configuration;
        // addExistingCurrencyConversion([currency_conversion]);
        get_rh_list(get_config);
      },
      error: function (xhr) {
        alert("An error occured: " + xhr.status + " " + xhr.statusText);
      },
      timeout: 30000
    });
  });

  $('#myModal').on('shown.bs.modal', function (e) {
    if ($(e.relatedTarget).attr('class') == "rh-absent") {
      $(".api-key-guide").addClass("d-none");
      $(".adapter-guide").removeClass("d-none");
      $('#admin-tab .slides img').css("width", "90%");
      $('#admin-tab .slides img').height($('.box-expand').height() - 140);
      $('#admin-tab .modal-content').height($('.box-expand').height() + 20);

      if ($("input[name='which-adapter']:checked").val() == "AWS") {
        $(".aws-guide").removeClass("d-none");
        $(".azure-guide").addClass("d-none");
      }
      else if ($("input[name='which-adapter']:checked").val() == "Azure") {
        $(".aws-guide").addClass("d-none");
        $(".azure-guide").removeClass("d-none");
      }
    }
    else {
      $(".api-key-guide").removeClass("d-none");
      $(".adapter-guide").addClass("d-none");
      $(".aws-guide").addClass("d-none");
      $(".azure-guide").addClass("d-none");
      $('#admin-tab .slides img').css("width", "85%");
      $('#admin-tab .slides img').height($('.box-expand').height() - 170);
      $('#admin-tab .modal-content').height($('.box-expand').height() - 35);
    }
    let widthOfModal = parseFloat($('.fluid-container').css("margin-left").slice(0, -2)) * 2;
    $('#admin-tab .modal-content').width($('#content').width() + widthOfModal);

    $('#admin-tab .modal-content').css("margin-inline", $('.fluid-container').css("padding-left"));
    // $('#admin-tab .slides').height($('#getting-started').height() - 180);\
    let changeImgId = $('.slider:not(.hidden) .active-img').attr("id");
    $(`a[href="#${changeImgId}"]`).css("background", "#3db5de");
  });

  $('#saveCredsForm').submit(function (e) {
    e.preventDefault();
    validateCreds();
  });

  $(document).on('click', '#refresh-page', function (e) {
    window.location.reload();
  });

  $(document).on('click', '#currency-conversion-new', function (e) {
    addNewCurrConv();
  });

  $(document).on('click', '.save-creds', function (e) {
    saveCreds();
  });

  // $(document).on('click', '.save-kumo-data', function (e) {
  //   saveKumoData(this);
  // });

  $(document).on('click', '#arrow-prev', function (e) {
    let changeImgId = $('.slider:not(.hidden) .active-img').attr("id");

    if ($('.slider:not(.hidden) .active-img').prev().length == 0) {
      $(`a[href="#${changeImgId}"]`).css("background", "#bab9b9");
      $('.slider:not(.hidden) .active-img').removeClass("active-img");
      $('.slider:not(.hidden) div').last().addClass("active-img");
      changeImgId = $('.slider:not(.hidden) .active-img').attr("id");
      $(`a[href="#${changeImgId}"]`).css("background", "#3db5de");
    }
    else {
      $(`a[href="#${changeImgId}"]`).css("background", "#bab9b9");
      $('.slider:not(.hidden) .active-img').removeClass("active-img").prev().addClass("active-img");
      changeImgId = $('.slider:not(.hidden) .active-img').attr("id");
      $(`a[href="#${changeImgId}"]`).css("background", "#3db5de");
    }
    $(`a[href="#${changeImgId}"]`).click();
  });

  $(document).on('click', '#arrow-next', function (e) {
    let changeImgId = $('.slider:not(.hidden) .active-img').attr("id");

    if ($('.slider:not(.hidden) .active-img').next().length == 0) {
      $(`a[href="#${changeImgId}"]`).css("background", "#bab9b9");
      $('.slider:not(.hidden) .active-img').removeClass("active-img");
      $($('.slider:not(.hidden) div')[1]).addClass("active-img");
      changeImgId = $('.slider:not(.hidden) .active-img').attr("id");
      $(`a[href="#${changeImgId}"]`).css("background", "#3db5de");
    }
    else {
      $(`a[href="#${changeImgId}"]`).css("background", "#bab9b9");
      $('.slider:not(.hidden) .active-img').removeClass("active-img").next().addClass("active-img");
      changeImgId = $('.slider:not(.hidden) .active-img').attr("id");
      $(`a[href="#${changeImgId}"]`).css("background", "#3db5de");
    }
    $(`a[href="#${changeImgId}"]`).click();
  });

  $(document).on('click', '.slider:not(.hidden) .fa-circle-o', function (e) {
    let clickedImg = $(e.target).attr("href");
    let clickedImgId = clickedImg.slice(1,);
    let oldImgId = $('.slider:not(.hidden) .active-img').attr("id");
    $('.slider:not(.hidden) .active-img').removeClass("active-img");
    $(`a[href="#${oldImgId}"]`).css("background", "#bab9b9");
    $(`.slider:not(.hidden) div[id="${clickedImgId}"]`).addClass("active-img");
    $(`a[href="${clickedImg}"]`).css("background", "#3db5de");
  });

  $(document).on('click', '#yes-edit', function (e) {
    $('.yes-creds').hide();
    $('.no-creds').show();
    $('.validate').show();
    $('.save-creds').show();
    $('input[name="kumo-domain-url"]').val($('.site-host').val());
    $('input[name="kumo-api-key"]').val($('.api-key').val());
    $('#savingStatus').text('');
    $(".hide-button").show();
    $("#cancel-edit").show();
  });

  $(document).on('click', '#cancel-edit', function (e) {
    $('.yes-creds').show();
    $('.no-creds').hide();
    $('.validate').hide();
    $('.save-creds').hide();
    $('#savingStatus').text('');
    $(".hide-button").hide();
    $("#cancel-edit").hide();
  });

  $(document).on("click", '#cust-edit', function (e) {
    $(".hide-button-cust").show();
    $(".save-cust").show();
    $(".save-cust").prop("disabled", false);
    $("#rightsizing_docs_url").prop("disabled", false);
    $(".hide-button-cust").show();

  });

  $(document).on("click", "#cancel-cust-edit", function (e) {
    $(".hide-button-cust").hide();
    $("#rightsizing_docs_url").prop("disabled", true);
  });

  $(document).on("click", '.save-cust', function (e) {

    let data = {"documentation_link": $('#rightsizing_docs_url')[0].value};
    saveCustomizations(data);
    $(".save-cust").hide(); // on success
    $(".hide-button-cust").hide();
    $("#rightsizing_docs_url").prop("disabled", true);
  });

  $(document).on('click', '#edit-setting', function (e) {
    setDisabled($('.enabling'), false);
    $('#update-configuration').text('');
    $(".hide-button-edit").show();
  });

  $(document).on('click', '#cancel-edit-config', function (e) {
    setDisabled($('.enabling'), true);
    $('#update-configuration').text('');
    $(".hide-button-edit").hide();
  });

  $(document).on('click', '.remove-new-cc', function (e) {
    $(`#block-new-${this.id.slice(11,)}`).remove();
    add_new_counter--;
  });

  // $(document).on('click', '#edit-conv-rate', function (e) {
  //   $('.curr-conv').prop("disabled", false);
  //   $('#update-currency-conv').text('');
  //   $(".hide-button-edit-conv-rate").show();
  // });

  $(document).on('click', '.cancel-edit-cr', function (e) {
    let clicked_id = this.id.substring(12,);
    $(`#cr-${clicked_id}`).addClass('d-none');
    setDisabled($(`#source-${clicked_id}, #target-${clicked_id}`), true);
    $(`#hide-button-edit-${clicked_id}`).addClass('d-none');
    $(`.curr-conv-${clicked_id}`).prop('disabled', true);
    $(`#update-currency-conv-${clicked_id}`).empty();
    $(`#cancel-edit-${clicked_id}`).text("Cancel Edit");
  });

  $(document).on('click', '.collapse-menu', function (e) {
    $("i", this).toggleClass("fa fa-chevron-right fa fa-chevron-down");
  });

  $(document).on('click', '#update-config', function (e) {
    updateConfig();
  });

  $(document).on('change', 'input[name="which-adapter"]', function (e) {
    if ($("input[name='which-adapter']:checked").val() == "AWS") {
      $(".aws-guide").removeClass("d-none");
      $(".azure-guide").addClass("d-none");
    }
    else if ($("input[name='which-adapter']:checked").val() == "Azure") {
      $(".aws-guide").addClass("d-none");
      $(".azure-guide").removeClass("d-none");
    }

    let currentImg = $('.slider:not(.hidden) .active-img').attr("id");
    $(`a[href="#${currentImg}"]`).css("background", "#bab9b9");
    $('.slider:not(.hidden) .active-img').removeClass("active-img");
    $($('.slider:not(.hidden) div')[1]).addClass("active-img");
    let changeImgId = $('.slider:not(.hidden) .active-img').attr("id");
    $(`a[href="#${changeImgId}"]`).click();
  });

})

function setConvRateMonths() {
  let last_12_months = [];
  var now = new Date();
  last_12_months.push(MONTH_NAMES[now.getMonth()].slice(0,3)+' '+now.getFullYear())
  for(var i=0; i<=10;i++){
    var past = now.setMonth(now.getMonth() - 1);
    last_12_months.push(MONTH_NAMES[now.getMonth()].slice(0,3)+' '+now.getFullYear())
  }

  return last_12_months;
}

function validateCreds() {
  loaderObjAdmin.display();
  $.ajax({
    url: "/xui/kumo/api/validate_credentials/",
    type: 'POST',
    dataType: 'json',
    data: {
      body: JSON.stringify({
        web_host: $('input[name="kumo-domain-url"]').val(),
        api_key: $('input[name="kumo-api-key"]').val(),
      })
    },
    success: function (response) {
      if (response.result) {
        $('#validationStatus').text('Credentials validated successfully!');
        $('.save-creds').prop('disabled', false);
        $('.save-creds').removeClass('disabled');
      }
      else {
        $('#validationStatus').text('Credentials not valid!');
        $('.save-creds').prop('disabled', true);
        $('.save-creds').addClass('disabled');
      }

      // loaderObjAdmin.hide();
    },
    error: function (xhr) {
      alert("An error occured: " + xhr.status + " " + xhr.statusText);
      // loaderObjAdmin.hide();
    }
  });
}

function saveCreds() {
  loaderObjAdmin.display();
  $.ajax({
    url: "/xui/kumo/api/save_credentials/",
    type: 'POST',
    dataType: 'json',
    data: {
      body: JSON.stringify({
        web_host: $('input[name="kumo-domain-url"]').val(),
        api_key: $('input[name="kumo-api-key"]').val(),
      })
    },
    success: function (response) {
      if (response.result) {
        if (response.exists) {
          $('#savingStatus').text('No changes in credentials!');
        }
        else if (response.changed) {
          $('#savingStatus').text('Credentials updated exists!');
        }
        else {
          $('#savingStatus').text('Credentials stored successfully!');
        }
        $('.validate, .save-creds').prop('disabled', true);
        $('.validate, .save-creds').addClass('disabled');
        $('#validationStatus').text('');

        getCreds(get_rh_list);
      }
      else {
        $('#savingStatus').text('Credentials not stored!');
      }

      // loaderObjAdmin.hide();
    },
    error: function (xhr) {
      alert("An error occured: " + xhr.status + " " + xhr.statusText);
      // loaderObjAdmin.hide();
    }
  });
}

// function saveKumoData(event) {
//   if (($(`input[name="billing-adapter-${event.id}"]`).val() == "")
//       && ($(`input[name="normal-adapter-${event.id}"]`).val() == "")) {
//           $(`#savingKumoData-${event.id}`).text('Please enter data to save!');
//   }
//   else {
//     $(`#savingKumoData-${event.id}`).text('');
//     loaderObjAdmin.display();

//     $.ajax({
//       url: "/xui/kumo/api/save_kumo_data/",
//       type: 'POST',
//       dataType: 'json',
//       data: {
//         body: JSON.stringify({
//           rhid: event.id,
//           billing_account: $(`input[name="billing-adapter-${event.id}"]`).val(),
//           normal_account: $(`input[name="normal-adapter-${event.id}"]`).val(),
//         })
//       },
//       success: function (response) {
//         if (response.result) {
//           $(`#savingKumoData-${event.id}`).text('Data Stored!');
//         }
//         else {
//           $(`#savingKumoData-${event.id}`).text('Data not stored!');
//         }

//         // loaderObjAdmin.hide();
//       },
//       error: function (xhr) {
//         alert("An error occured: " + xhr.status + " " + xhr.statusText);
//         // loaderObjAdmin.hide();
//       }
//     });
//   }
// }

function getCreds(func1) {
  loaderObjAdmin.display();
  $.ajax({
    url: "/xui/kumo/api/get_credentials/",
    type: 'POST',
    dataType: 'json',
    data: {},
    success: function (response) {
      $(".show-refresh").hide();
      $(".hide-refresh").show();
      $("a[href='#resource-handlers']").parent().show();
      $("#cancel-edit").hide();
      $("hr").show();
      if ((response.result) && (response.creds.length != 0)) {
        $('.yes-creds').show();
        $('.no-creds').hide();
        $('.validate').hide();
        $('.save-creds').hide();
        $('.site-host').val(`https://${response.creds['web_host']}`);
        $('.api-key').val(response.creds['api_key'].slice(0,30));
        $(".hide-button").hide();
        $("#yes-edit").show();
        $('.rh-absent').addClass('d-none');
        func1(get_config);
      }
      else {
        $('.yes-creds').hide();
        $('.no-creds').show();
        $('.validate').show();
        $('.save-creds').show();
        $(".hide-button").show();
        $("#yes-edit").hide();
        $('.rh-list-group').empty();
        $('#no-rh-list').text('No resource handlers found!');
        $('#no-rh-list').removeClass('d-none');
        $('.rh-absent').removeClass('d-none');
        // loaderObjAdmin.hide();
      }
    },
    error: function (xhr) {
      $('.yes-creds').hide();
      $('.no-creds').show();
      $('.validate').show();
      $('.save-creds').show();
      $(".hide-button").show();
      $("#cancel-edit").hide();
      $("#yes-edit").hide();
      if(xhr.status == 404) {
        $(".show-refresh").show();
        $(".hide-refresh").hide();
        $("hr").hide();
      }
      $("a[href='#resource-handlers']").parent().hide();
      // loaderObjAdmin.hide();
    },
    timeout: 30000
  });
}

function get_rh_list(func2) {
  $.ajax({
    url: "/xui/kumo/api/get_rh_list/",
    type: 'POST',
    dataType: 'json',
    data: {
        body: JSON.stringify({
            show_all: 'true',
            not_configured: 'true',
        })
    },
    success: function (response) {
      $(".show-refresh").hide();
      $(".hide-refresh").show();
      $("a[href='#resource-handlers']").parent().show();
      $('.rh-list-group').empty();
      $('#no-rh-list').addClass('d-none');
      $('.rh-absent').addClass('d-none');
      let count_cc_required = 0;
      let currency_unified = false;

      if (response.result.length != 0) {
        $("#alert-box-invali-creds").hide();
        response.result.forEach(rh => {
          let rh_list_str = "";
          let iconName = "";
          if (rh.th_type.split(".")[0] == "AWS") {
            iconName = "icon-handler-aws";
          }
          else if (rh.th_type.split(".")[0] == "GCP") {
            iconName = "icon-handler-gcp";
          }
          else if (rh.th_type.split(".")[0] == "Azure") {
            iconName = "icon-handler-azure_arm";
          }

          let placeHolder = (rh.th_type.split(".")[0] == "AWS") ? "Account ID" : "Subscription ID";
          let inputPattern = (rh.th_type.split(".")[0] == "AWS") ? "^[0-9]{12}$" : "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$";
          let directButtons = "";
          if (iconName == "icon-handler-azure_arm") {
            directButtons = `
              <button class="btn btn-primary"
                      onclick="location.href='/admin/resourcehandlers/${rh.id}/#tab-spend';"
                      type="button">Spend</button>
              <button class="btn btn-primary"
                      onclick="location.href='/admin/resourcehandlers/${rh.id}/#tab-efficiency';"
                      type="button">Efficiency</button>
              <button class="btn btn-primary"
                      onclick="location.href='/admin/resourcehandlers/${rh.id}/#tab-compliance';"
                      type="button">Compliance</button>`
          }
          else if (iconName == "icon-handler-gcp") {
            directButtons = `
              <button class="btn btn-primary"
                    onclick="location.href='/admin/resourcehandlers/${rh.id}/#tab-spend';"
                    type="button">Spend</button>
              <button class="btn btn-primary"
                    onclick="location.href='/admin/resourcehandlers/${rh.id}/#tab-efficiency';"
                    type="button">Efficiency</button>`
          }
          else if (iconName == "icon-handler-aws") {
            directButtons = `
              <button class="btn btn-primary"
                      onclick="location.href='/admin/resourcehandlers/${rh.id}/#tab-spend';"
                      type="button">Spend</button>
              <button class="btn btn-primary"
                      onclick="location.href='/admin/resourcehandlers/${rh.id}/#tab-efficiency';"
                      type="button">Efficiency</button>
              <button class="btn btn-primary"
                      onclick="location.href='/admin/resourcehandlers/${rh.id}/#tab-compliance';"
                      type="button">Compliance</button>`
          }

          rh_list_str = rh_list_str + `
              <div class="accordion-item">
                  <div class="accordion-header">
                      <h4 class="panel-title">
                          <a class="collapse-menu" data-bs-toggle="collapse" href="#collapse-${rh.id}" style="float: left; margin-right:15px; margin-top: 7px; padding: 0 0 0 0;">
                              <i class="fa fa-chevron-right"></i>
                          </a>
                          <div style="float: left; margin-top: 5px;">
                              <a>
                                  <span class="icon icon-30 ${iconName}"></span>
                                  ${rh.name}
                              </a>
                              <span id="cc-avail-${rh.id}"></span>
                          </div>
                          <div style="float: right;">
                              ${directButtons}
                          </div>
                      </h4>
                  </div>
                  <div id="collapse-${rh.id}" class="accordion-collapse collapse">
                      <div class="accordion-body p-0">
                      <table class="table">
                          <thead>
                              <tr>
                                  <th><strong>Provider</strong></th>
                                  <th><strong>Provider ID</strong></th>
                                  <th><strong>Provider Currency</strong></th>
                                  <th><strong>CMP Description</strong></th>
                              </tr>
                          </thead>
                          <tbody>
                              <tr>
                                  <td>${rh.th_type}</td>
                                  <td>${rh.provider_id}</td>
                                  <td>${rh.default_currency}</td>
                                  <td>${rh.description || "--"}</td>
                              </tr>
          `;

          if ((rh.available_cc) && (rh.default_currency != rh.set_currency)) {
            rh_list_str = rh_list_str + `
              <tr>
                <td colspan="4">
                  <div id="block-${rh.id}-${rh.available_cc.id}">
                    <div class="mb-3 combo">
                      <div class="col-sm-12" style="display: flex; align-items: flex-end;">
                          <label style="width: 18%">Preferred currency:</label>
                          <select class="form-control selectize curr-conv" id="source-${rh.id}-${rh.available_cc.id}" style="width: 15%; margin-left: -7px;" disabled>
                              <option value="" selected disabled>Select Source Currency</option>
                              <option value="USD">US dollar(USD)</option>
                              <option value="EUR">Euro(EUR)</option>
                              <option value="CHF">Swiss franc(CHF)</option>
                              <option value="ARS">Argentine peso(ARS)</option>
                              <option value="AUD">Australian dollar(AUD)</option>
                              <option value="DKK">Danish krone(DKK)</option>
                              <option value="CAD">Canadian dollar(CAD)</option>
                              <option value="IDR">Indonesian rupiah(IDR)</option>
                              <option value="JPY">Japanese yen(JPY)</option>
                              <option value="KRW">Korea (South) Won(KRW)</option>
                              <option value="NZD">New Zealand Dollars(NZD)</option>
                              <option value="NOK">Norwegian krone(NOK)</option>
                              <option value="RUR">Russian Ruble(RUR)</option>
                              <option value="SAR">Saudi Riyal(SAR)</option>
                              <option value="ZAR">South African Rand(ZAR)</option>
                              <option value="SEK">Swedish krona(SEK)</option>
                              <option value="TWD">New Taiwan dollar(TWD)</option>
                              <option value="TRY">Turkish lira(TRY)</option>
                              <option value="GBP">British pound(GBP)</option>
                              <option value="MXN">Mexican peso(MXN)</option>
                              <option value="MYR">Malaysian ringgit(MYR)</option>
                              <option value="INR">Indian rupee(INR)</option>
                              <option value="HKD">Hong Kong dollar(HKD)</option>
                              <option value="BRL">Brazilian real(BRL)</option>
                              <option value="CNY">Chinese Yuan(CNY)</option>
                          </select>
                          <i class="fas fa-long-arrow-right fa-2x" style="margin-inline: 3%;"></i>
                          <label style="width: 18%">Target currency:</label>
                          <select class="form-control selectize curr-conv" id="target-${rh.id}-${rh.available_cc.id}" style="width: 15%; margin-left: -7px;" disabled>
                              <option value="" selected disabled>Select Target Currency</option>
                              <option value="USD">US dollar(USD)</option>
                              <option value="EUR">Euro(EUR)</option>
                              <option value="CHF">Swiss franc(CHF)</option>
                              <option value="ARS">Argentine peso(ARS)</option>
                              <option value="AUD">Australian dollar(AUD)</option>
                              <option value="DKK">Danish krone(DKK)</option>
                              <option value="CAD">Canadian dollar(CAD)</option>
                              <option value="IDR">Indonesian rupiah(IDR)</option>
                              <option value="JPY">Japanese yen(JPY)</option>
                              <option value="KRW">Korea (South) Won(KRW)</option>
                              <option value="NZD">New Zealand Dollars(NZD)</option>
                              <option value="NOK">Norwegian krone(NOK)</option>
                              <option value="RUR">Russian Ruble(RUR)</option>
                              <option value="SAR">Saudi Riyal(SAR)</option>
                              <option value="ZAR">South African Rand(ZAR)</option>
                              <option value="SEK">Swedish krona(SEK)</option>
                              <option value="TWD">New Taiwan dollar(TWD)</option>
                              <option value="TRY">Turkish lira(TRY)</option>
                              <option value="GBP">British pound(GBP)</option>
                              <option value="MXN">Mexican peso(MXN)</option>
                              <option value="MYR">Malaysian ringgit(MYR)</option>
                              <option value="INR">Indian rupee(INR)</option>
                              <option value="HKD">Hong Kong dollar(HKD)</option>
                              <option value="BRL">Brazilian real(BRL)</option>
                              <option value="CNY">Chinese Yuan(CNY)</option>
                          </select>
                          <i class="fas fa-edit fa-lg edit-conversion" id="edit-${rh.id}-${rh.available_cc.id}" data-bs-toggle="tooltip" data-bs-placement="top" data-bs-html="true" title="Edit this setting!" style="padding-bottom: 10px;padding-left: 10px;border-bottom: 0;font-weight: 100;cursor: pointer;"></i> <i class="fa fa-times-circle fa-lg delete-conversion" aria-hidden="true" data-bs-toggle="tooltip" data-bs-placement="top" data-bs-html="true" title="Delete this currency conversion!" style="padding-bottom: 10px;padding-left: 10px;border-bottom: 0;font-weight: 100;cursor: pointer;"></i>
                          <div class="d-none">
                              <button class="btn btn-danger sure-remove-cc" type="button" id="delete-${rh.id}-${rh.available_cc.id}" data-ccid="${rh.available_cc.id}" style="margin-inline: 10px;">Delete for sure!</button>
                              <button class="btn btn-light not-sure-remove-cc" type="button">Cancel</button>
                          </div>
                      </div>
                      <div class="col-sm-12 sub-headings d-none" id="cr-${rh.id}-${rh.available_cc.id}" style="display: flex;align-items: flex-end;margin-top: 1%;">
                          <label style="width: 20%">Conversion rate:</label>
                          <div class="col-sm-12" style="display: flex;" id="months-${rh.id}-${rh.available_cc.id}"></div>
                      </div>
                      <p style="display: none; color: red; margin: 15px; font-weight: 700;" id="update-currency-error"></p>
                      <div class="mb-3 col-sm-12 d-none" id="hide-button-edit-${rh.id}-${rh.available_cc.id}" style="display: inline-flex; margin-top: 15px;margin-bottom: 0;">
                        <div style="margin-inline: 15px;">
                            <button class="btn btn-success update-conversion" type="button" id="update-${rh.id}-${rh.available_cc.id}" data-ccid="${rh.available_cc.id}">Update Conversion Rates</button>
                            <label id="update-currency-conv-${rh.id}-${rh.available_cc.id}"></label>
                        </div>
                        <div>
                            <button class="btn btn-light cancel-edit-cr" type="button" id="cancel-edit-${rh.id}-${rh.available_cc.id}">Cancel Edit</button>
                        </div>
                    </div>
                    </div>
                  </div>
                </td>
              </tr>
          `
          }
          else if (rh.default_currency != rh.set_currency) {
            count_cc_required++;
            rh_list_str = rh_list_str + `
              <tr>
                <td colspan="4">
                  <div id="block-new-${rh.id}">
                    <div class="mb-3 combo">
                      <div class="col-sm-12" id="add-icon-${rh.id}" style="display: flex; align-items: flex-end;">
                          <label style="width: 18%">Preferred currency:</label>
                          <select class="form-control selectize curr-conv" id="source-new-${rh.id}" style="width: 15%; margin-left: -7px;">
                              <option value="" selected disabled>Select Source Currency</option>
                              <option value="USD">US dollar(USD)</option>
                              <option value="EUR">Euro(EUR)</option>
                              <option value="CHF">Swiss franc(CHF)</option>
                              <option value="ARS">Argentine peso(ARS)</option>
                              <option value="AUD">Australian dollar(AUD)</option>
                              <option value="DKK">Danish krone(DKK)</option>
                              <option value="CAD">Canadian dollar(CAD)</option>
                              <option value="IDR">Indonesian rupiah(IDR)</option>
                              <option value="JPY">Japanese yen(JPY)</option>
                              <option value="KRW">Korea (South) Won(KRW)</option>
                              <option value="NZD">New Zealand Dollars(NZD)</option>
                              <option value="NOK">Norwegian krone(NOK)</option>
                              <option value="RUR">Russian Ruble(RUR)</option>
                              <option value="SAR">Saudi Riyal(SAR)</option>
                              <option value="ZAR">South African Rand(ZAR)</option>
                              <option value="SEK">Swedish krona(SEK)</option>
                              <option value="TWD">New Taiwan dollar(TWD)</option>
                              <option value="TRY">Turkish lira(TRY)</option>
                              <option value="GBP">British pound(GBP)</option>
                              <option value="MXN">Mexican peso(MXN)</option>
                              <option value="MYR">Malaysian ringgit(MYR)</option>
                              <option value="INR">Indian rupee(INR)</option>
                              <option value="HKD">Hong Kong dollar(HKD)</option>
                              <option value="BRL">Brazilian real(BRL)</option>
                              <option value="CNY">Chinese Yuan(CNY)</option>
                          </select>
                          <i class="fas fa-long-arrow-right fa-2x" style="margin-inline: 3%;"></i>
                          <label style="width: 18%">Target currency:</label>
                          <select class="form-control selectize curr-conv" id="target-new-${rh.id}" style="width: 15%; margin-left: -7px;">
                              <option value="" selected disabled>Select Target Currency</option>
                              <option value="USD">US dollar(USD)</option>
                              <option value="EUR">Euro(EUR)</option>
                              <option value="CHF">Swiss franc(CHF)</option>
                              <option value="ARS">Argentine peso(ARS)</option>
                              <option value="AUD">Australian dollar(AUD)</option>
                              <option value="DKK">Danish krone(DKK)</option>
                              <option value="CAD">Canadian dollar(CAD)</option>
                              <option value="IDR">Indonesian rupiah(IDR)</option>
                              <option value="JPY">Japanese yen(JPY)</option>
                              <option value="KRW">Korea (South) Won(KRW)</option>
                              <option value="NZD">New Zealand Dollars(NZD)</option>
                              <option value="NOK">Norwegian krone(NOK)</option>
                              <option value="RUR">Russian Ruble(RUR)</option>
                              <option value="SAR">Saudi Riyal(SAR)</option>
                              <option value="ZAR">South African Rand(ZAR)</option>
                              <option value="SEK">Swedish krona(SEK)</option>
                              <option value="TWD">New Taiwan dollar(TWD)</option>
                              <option value="TRY">Turkish lira(TRY)</option>
                              <option value="GBP">British pound(GBP)</option>
                              <option value="MXN">Mexican peso(MXN)</option>
                              <option value="MYR">Malaysian ringgit(MYR)</option>
                              <option value="INR">Indian rupee(INR)</option>
                              <option value="HKD">Hong Kong dollar(HKD)</option>
                              <option value="BRL">Brazilian real(BRL)</option>
                              <option value="CNY">Chinese Yuan(CNY)</option>
                          </select>
                      </div>
                      <div class="col-sm-12 sub-headings" id="cr-new-${rh.id}" style="display: flex;align-items: flex-end;margin-top: 1%;">
                          <label style="width: 20%">Conversion rate:</label>
                          <div class="col-sm-12" style="display: flex;" id="months-new-${rh.id}"></div>
                      </div>
                      <p style="display: none; color: red; margin: 15px; font-weight: 700;" id="add-currency-error"></p>
                      <div class="mb-3 col-sm-12" id="hide-button-edit-new-${rh.id}" style="display: inline-flex; margin-top: 15px;margin-bottom: 0;">
                        <div style="margin-inline: 15px;">
                            <button class="btn btn-success add-conversion" type="button" id="add-new-${rh.id}" data-provider="${rh.th_type}">Add Conversion Rate</button>
                            <label id="add-currency-conv-${rh.id}"></label>
                        </div>
                    </div>
                    </div>
                  </div>
                </td>
              </tr>
            `
          }
          else if ((rh.default_currency == rh.set_currency) && (rh.default_currency == "")) {
            rh_list_str = rh_list_str + `
              <tr>
                <td colspan="4">
                  No Provider currency found, Please add at least environment to this resource handler if does not exist and run 'CSMP Resource Handler Data Caching' recurring job show above & check again. 
                </td>
              </tr>
            `
          }
          else {
            rh_list_str = rh_list_str + `
              <tr>
                <td colspan="4">
                  No conversion required as provider currency (${rh.default_currency}) and preferred currency (${rh.set_currency}) are same!
                </td>
              </tr>
            `
          }

          rh_list_str = rh_list_str + `
                          </tbody>
                      </table>
                      </div>
                  </div>
              </div>
          `
          $('.rh-list-group').append(rh_list_str);

          if ((rh.available_cc) && (rh.default_currency != rh.set_currency)) {
            $(`#source-${rh.id}-${rh.available_cc.id}`).val(rh.available_cc.cloud_provider_currency);
            $(`#target-${rh.id}-${rh.available_cc.id}`).val(rh.available_cc.default_currency);
            // $(`#cc-avail-${rh.id}`).text("Currency conv. available!");
            // $(`#cc-avail-${rh.id}`).addClass("cc-avail");
            last_12_months_cc.forEach(month => {
              const d = new Date(month);
              let month_no = ((d.getMonth()+1) < 10) ? `0${d.getMonth()+1}` : d.getMonth()+1;
              let month_name = `${d.getFullYear()}-${month_no}`
              $(`#months-${rh.id}-${rh.available_cc.id}`).append(`
                <div>
                  <div><label class="form-label">${month}</label></div>
                  <div><input type="text" min="0" class="curr-conv-${rh.id}-${rh.available_cc.id}" id="${rh.id}-${rh.available_cc.id}-${month.slice(0,3)}" style="width: 70%;" value="${rh.available_cc.exchange_rates[month_name]}" disabled></div>
                </div>
              `)
            });
          }
          else if (rh.default_currency != rh.set_currency) {
            $(`#source-new-${rh.id}`).val(rh.default_currency);
            $(`#target-new-${rh.id}`).val(rh.set_currency);
            if (rh.set_currency) {
              $(`#cc-avail-${rh.id}`).text(`(${rh.default_currency} -> ${rh.set_currency}) conversion rate not available!`);
            }
            else {
              $(`#cc-avail-${rh.id}`).text("Please set 'Preferred Currency' to show currency on dashboard widgets!");
            }

            $(`#cc-avail-${rh.id}`).addClass("cc-not-avail");
            last_12_months_cc.forEach(month => {
              $(`#months-new-${rh.id}`).append(`
                <div>
                  <div><label class="form-label">${month}</label></div>
                  <div><input type="text" min="0" class="curr-conv-${rh.id}" id="${rh.id}-${month.slice(0,3)}" style="width: 70%;"></div>
                </div>
              `)
            });
          }
          else {
            $(`#cc-avail-${rh.id}`).empty();
          }

          $(`input[name="billing-adapter-${rh.id}"]`).val(rh.billing_account);
          $(`input[name="normal-adapter-${rh.id}"]`).val(rh.normal_account);
        });

        if (count_cc_required == 0) {
          currency_unified = true;
          $("#alert-box-rj-info").show();
        }
        else {
          currency_unified = false;
          $("#alert-box-rj-info").hide();
        }

        $.ajax({
          url: "/xui/kumo/api/set_currency_unified_status/",
          type: 'POST',
          dataType: 'json',
          data: {
              body: JSON.stringify({
                currency_unified: currency_unified
              })
          },
          success: function (response) {}
        })
        func2();
      }
      else {
        if (response.hasOwnProperty('error_message')) {
          $("#alert-box-invali-creds").show();
          $('.rh-list-group').empty();
          $('#no-rh-list').text('No resource handlers found!');
          $('#no-rh-list').removeClass('d-none');
          $('.rh-absent').removeClass('d-none');
        }
        else if (response.result.length == 0) {
          $('.rh-list-group').empty();
          $('#no-rh-list').text('No resource handlers found!');
          $('#no-rh-list').removeClass('d-none');
          $('.rh-absent').removeClass('d-none');
          func2();
        }
      }
    },
    error: function (xhr) {
      if(xhr.status == 404) {
        $(".show-refresh").show();
        $(".hide-refresh").hide();
      }
      $("a[href='#resource-handlers']").parent().hide();
      // loaderObjAdmin.hide();
    },
    timeout: 30000
  });
}

function saveCustomizations(data) {
  $.ajax({
    url: "/xui/kumo/api/save_documentation_link/",
    type: 'POST',
    dataType: 'json',
    data: data,
    success: function (response) {
      showAlert("Saved Successfully. Refresh the Cost Tab to see the change", "alert-success");
    },
        error: function (xhr) {
      showAlert("Error saving file: " + xhr.statusText, "alert-danger");
    }
  });
}

function get_config() {
  $.ajax({
    url: "/xui/kumo/api/get_config/",
    type: 'GET',
    dataType: 'json',
    data: {},
    success: function (response) {
      $(".show-refresh").hide();
      $(".hide-refresh").show();
      $("a[href='#resource-handlers']").parent().show();

      if (response.hasOwnProperty('error')) {
        // loaderObjAdmin.hide();
        $("#edit-setting").hide();
      }
      else if (response.result.length == 0) {
        $("#edit-setting").hide();
      }
      else {
        $("#edit-setting").show();
        let adviser_config = response.result.service_adviser_config;
        (adviser_config.rds_snapshot_config_check) ? $("#rds_snapshot_no").prop("checked", true) : $("#rds_snapshot_no").prop("checked", false);
        (adviser_config.running_rightsizing_config_check) ? $("#idle_running_rs").prop("checked", true) : $("#idle_running_rs").prop("checked", false);
        (adviser_config.stopped_rightsizing_config_check) ? $("#idle_stopped_rs").prop("checked", true) : $("#idle_stopped_rs").prop("checked", false);
        (adviser_config.volume_snapshot_config_check) ? $("#volume_snapshot_no").prop("checked", true) : $("#volume_snapshot_no").prop("checked", false);
        $("#rds_snapshot_after").val(adviser_config.rds_snapshot_retention_period);
        $("#volume_snapshot_after").val(adviser_config.volume_snapshot_retention_period);
        $("#idle_running_after").val(adviser_config.running_rightsizing_retention_period);
        $("#idle_stopped_after").val(adviser_config.stopped_rightsizing_retention_period);
        $("#currency-conversion-new").show();

        if (Object.keys(response.result).includes("default_currency")) {
          $(".no-data-cc").empty();
          // $('.setting-currency-conversion').empty();
          // $(`#pref-curr`).empty();
          // $(`#pref-curr`).append(`<option value="" selected disabled>Select Preferred Currency</option>`);
          // let currency_conversion = response.result.currency_configurations;
          // addExistingCurrencyConversion(currency_conversion);
        }
        else {
          $(".no-data-cc").html(`<label class="form-label">No preferred currency set!</label>`);
          $('.setting-currency-conversion').empty();
        }

        // if (Object.keys(response.result).includes("enable_currency_conversion")) {
        //   if (response.result.enable_currency_conversion) {
        //     $("#cc-status").parent().removeClass("off");
        //     $("#cc-status").parent().removeClass("btn-default");
        //     $("#cc-status").parent().addClass("btn-primary");
        //     $("#cc-status").prop("checked", true)
        //   }
        //   else {
        //     $("#cc-status").parent().addClass("off");
        //     $("#cc-status").parent().addClass("btn-default");
        //     $("#cc-status").parent().removeClass("btn-primary");
        //     $("#cc-status").prop("checked", false)
        //   }
        // }

        if (Object.keys(response.result).includes("default_currency")) {
          response.result.default_currency ? $("#pref-curr").val(response.result.default_currency) : $("#pref-curr").val("");
          preferredCurrency = response.result.default_currency;
        }

        // if (!$("#cc-status").prop("checked")) {
        //   // $(".currency-preference").addClass("d-none");
        //   $("#pref-curr").val("");
        // }
        // else {
        //   // $(".currency-preference").removeClass("d-none");
        //   if (!response.result.default_currency) {
        //     $("#pref-curr").val("");
        //     $("#edit-pref-curr").click();
        //   }
        // }
        // loaderObjAdmin.hide();
      }
    },
    error: function (xhr) {
      if(xhr.status == 404) {
        $(".show-refresh").show();
        $(".hide-refresh").hide();
        $("a[href='#resource-handlers']").parent().hide();
      }
      $("#edit-setting").hide();
      // loaderObjAdmin.hide();
    },
    timeout: 30000
  });
}

// function addExistingCurrencyConversion(currency_conversion) {
//   currency_conversion.forEach(cc => {
//     $('.setting-currency-conversion').append(`
//       <div style="border-bottom: 1px solid #eee;margin-top: 15px;" id="block-${cc.id}">
//         <div class="mb-3 combo">
//           <div class="col-sm-12" style="display: flex; align-items: flex-end;">
//               <label style="width: 18%">Preferred currency:</label>
//               <select class="form-control selectize curr-conv" id="source-${cc.id}" style="width: 15%; margin-left: -7px;" disabled>
//                   <option value="" selected disabled>Select Source Currency</option>
//                   <option value="USD">US dollar(USD)</option>
//                   <option value="EUR">Euro(EUR)</option>
//                   <option value="CHF">Swiss franc(CHF)</option>
//                   <option value="ARS">Argentine peso(ARS)</option>
//                   <option value="AUD">Australian dollar(AUD)</option>
//                   <option value="DKK">Danish krone(DKK)</option>
//                   <option value="CAD">Canadian dollar(CAD)</option>
//                   <option value="IDR">Indonesian rupiah(IDR)</option>
//                   <option value="JPY">Japanese yen(JPY)</option>
//                   <option value="KRW">Korea (South) Won(KRW)</option>
//                   <option value="NZD">New Zealand Dollars(NZD)</option>
//                   <option value="NOK">Norwegian krone(NOK)</option>
//                   <option value="RUR">Russian Ruble(RUR)</option>
//                   <option value="SAR">Saudi Riyal(SAR)</option>
//                   <option value="ZAR">South African Rand(ZAR)</option>
//                   <option value="SEK">Swedish krona(SEK)</option>
//                   <option value="TWD">New Taiwan dollar(TWD)</option>
//                   <option value="TRY">Turkish lira(TRY)</option>
//                   <option value="GBP">British pound(GBP)</option>
//                   <option value="MXN">Mexican peso(MXN)</option>
//                   <option value="MYR">Malaysian ringgit(MYR)</option>
//                   <option value="INR">Indian rupee(INR)</option>
//                   <option value="HKD">Hong Kong dollar(HKD)</option>
//                   <option value="BRL">Brazilian real(BRL)</option>
//                   <option value="CNY">Chinese Yuan(CNY)</option>
//               </select>
//               <i class="fas fa-long-arrow-right fa-2x" style="margin-inline: 3%;"></i>
//               <label style="width: 18%">Target currency:</label>
//               <select class="form-control selectize curr-conv" id="target-${cc.id}" style="width: 15%; margin-left: -7px;" disabled>
//                   <option value="" selected disabled>Select Target Currency</option>
//                   <option value="USD">US dollar(USD)</option>
//                   <option value="EUR">Euro(EUR)</option>
//                   <option value="CHF">Swiss franc(CHF)</option>
//                   <option value="ARS">Argentine peso(ARS)</option>
//                   <option value="AUD">Australian dollar(AUD)</option>
//                   <option value="DKK">Danish krone(DKK)</option>
//                   <option value="CAD">Canadian dollar(CAD)</option>
//                   <option value="IDR">Indonesian rupiah(IDR)</option>
//                   <option value="JPY">Japanese yen(JPY)</option>
//                   <option value="KRW">Korea (South) Won(KRW)</option>
//                   <option value="NZD">New Zealand Dollars(NZD)</option>
//                   <option value="NOK">Norwegian krone(NOK)</option>
//                   <option value="RUR">Russian Ruble(RUR)</option>
//                   <option value="SAR">Saudi Riyal(SAR)</option>
//                   <option value="ZAR">South African Rand(ZAR)</option>
//                   <option value="SEK">Swedish krona(SEK)</option>
//                   <option value="TWD">New Taiwan dollar(TWD)</option>
//                   <option value="TRY">Turkish lira(TRY)</option>
//                   <option value="GBP">British pound(GBP)</option>
//                   <option value="MXN">Mexican peso(MXN)</option>
//                   <option value="MYR">Malaysian ringgit(MYR)</option>
//                   <option value="INR">Indian rupee(INR)</option>
//                   <option value="HKD">Hong Kong dollar(HKD)</option>
//                   <option value="BRL">Brazilian real(BRL)</option>
//                   <option value="CNY">Chinese Yuan(CNY)</option>
//               </select>
//               <i class="fas fa-edit fa-lg edit-conversion" id="edit-${cc.id}" data-toggle="tooltip" data-placement="top" data-html="true" title="" data-original-title="Edit this setting!" style="padding-bottom: 10px;padding-left: 10px;border-bottom: 0;font-weight: 100;cursor: pointer;"></i> <i class="fa fa-times-circle fa-lg delete-conversion" aria-hidden="true" data-toggle="tooltip" data-placement="top" data-html="true" data-original-title="Delete this currency conversion!" style="padding-bottom: 10px;padding-left: 10px;border-bottom: 0;font-weight: 100;cursor: pointer;"></i>
//               <div class="d-none">
//                   <button class="btn btn-danger sure-remove-cc" type="button" id="delete-${cc.id}" style="margin-inline: 10px;">Delete for sure!</button>
//                   <button class="btn btn-default not-sure-remove-cc" type="button">Cancel</button>
//               </div>
//           </div>
//           <div class="col-sm-12 sub-headings hidden" id="cr-${cc.id}" style="display: flex;align-items: flex-end;margin-top: 1%;">
//               <label style="width: 20%">Conversion rate:</label>
//               <div class="col-sm-12" style="display: flex;" id="months-${cc.id}"></div>
//           </div>
//           <div class="form-group col-sm-12 hidden" id="hide-button-edit-${cc.id}" style="display: inline-flex; margin-top: 15px;margin-bottom: 0;">
//             <div style="margin-inline: 15px;">
//                 <button class="btn btn-success update-conversion" type="button" id="update-${cc.id}">Update Conversion Rates</button>
//                 <label id="update-currency-conv-${cc.id}"></label>
//             </div>
//             <div>
//                 <button class="btn btn-light cancel-edit-cr" type="button" id="cancel-edit-${cc.id}">Cancel Edit</button>
//             </div>
//         </div>
//         </div>
//       </div>
//     `);

//     $(`#source-${cc.id}`).val(cc.cloud_provider_currency);
//     $(`#target-${cc.id}`).val(cc.default_currency);
//     $(`#pref-curr`).append(`<option value="${cc.default_currency}">${CURRENCY_TO_NAME[cc.default_currency]}</option>`)
//     last_12_months_cc.forEach(month => {
//       const d = new Date(month);
//       let month_no = ((d.getMonth()+1) < 10) ? `0${d.getMonth()+1}` : d.getMonth()+1;
//       let month_name = `${d.getFullYear()}-${month_no}`
//       $(`#months-${cc.id}`).append(`
//         <div>
//           <div><label class="form-label">${month}</label></div>
//           <div><input type="number" min="0" class="curr-conv-${cc.id}" id="${cc.id}-${month.slice(0,3)}" style="width: 70%;" value="${cc.exchange_rates[month_name]}" disabled></div>
//         </div>
//       `)
//     });
//   });
//   if ($("#pref-curr option").length > 1) {
//     $("#pref-curr-label").addClass("d-none");
//     $("#pref-curr option").each(function() {
//       $(this).siblings('[value="'+ this.value +'"]').remove();
//     });
//   }
//   else {
//     $("#pref-curr-label").removeClass("d-none");
//   }

// }

function updateConfig() {
  loaderObjAdmin.display();
  $.ajax({
    url: "/xui/kumo/api/set_config/",
    type: 'POST',
    dataType: 'json',
    data:
    {
      body: JSON.stringify({
        right_size_config: {
            rds_snapshot_config_check: $("#rds_snapshot_no").prop("checked"),
            rds_snapshot_retention_period: $("#rds_snapshot_after").val(),
            running_rightsizing_config_check: $("#idle_running_rs").prop("checked"),
            running_rightsizing_retention_period: $("#idle_running_after").val(),
            stopped_rightsizing_config_check: $("#idle_stopped_rs").prop("checked"),
            stopped_rightsizing_retention_period: $("#idle_stopped_after").val(),
            volume_snapshot_config_check: $("#volume_snapshot_no").prop("checked"),
            volume_snapshot_retention_period: $("#volume_snapshot_after").val()
          }
        })
    },
    success: function (response) {
      $('#update-configuration').text("Updated Successfully!");
      // loaderObjAdmin.hide();
    },
    error: function (xhr) {
      alert("An error occured: " + xhr.status + " " + xhr.statusText);
      // loaderObjAdmin.hide();
    }
  });
}

// function addNewCurrConv() {
//   add_new_counter++;
//   $('.setting-currency-conversion').append(`
//     <div style="border-bottom: 1px solid #eee;margin-top: 15px;" id="block-new-${add_new_counter}">
//       <div class="mb-3 combo">
//         <div class="col-sm-12" id="add-icon-${add_new_counter}" style="display: flex; align-items: flex-end;">
//             <label style="width: 18%">Preferred currency:</label>
//             <select class="form-control selectize curr-conv" id="source-new-${add_new_counter}" style="width: 15%; margin-left: -7px;">
//                 <option value="" selected disabled>Select Source Currency</option>
//                 <option value="USD">US dollar(USD)</option>
//                 <option value="EUR">Euro(EUR)</option>
//                 <option value="CHF">Swiss franc(CHF)</option>
//                 <option value="ARS">Argentine peso(ARS)</option>
//                 <option value="AUD">Australian dollar(AUD)</option>
//                 <option value="DKK">Danish krone(DKK)</option>
//                 <option value="CAD">Canadian dollar(CAD)</option>
//                 <option value="IDR">Indonesian rupiah(IDR)</option>
//                 <option value="JPY">Japanese yen(JPY)</option>
//                 <option value="KRW">Korea (South) Won(KRW)</option>
//                 <option value="NZD">New Zealand Dollars(NZD)</option>
//                 <option value="NOK">Norwegian krone(NOK)</option>
//                 <option value="RUR">Russian Ruble(RUR)</option>
//                 <option value="SAR">Saudi Riyal(SAR)</option>
//                 <option value="ZAR">South African Rand(ZAR)</option>
//                 <option value="SEK">Swedish krona(SEK)</option>
//                 <option value="TWD">New Taiwan dollar(TWD)</option>
//                 <option value="TRY">Turkish lira(TRY)</option>
//                 <option value="GBP">British pound(GBP)</option>
//                 <option value="MXN">Mexican peso(MXN)</option>
//                 <option value="MYR">Malaysian ringgit(MYR)</option>
//                 <option value="INR">Indian rupee(INR)</option>
//                 <option value="HKD">Hong Kong dollar(HKD)</option>
//                 <option value="BRL">Brazilian real(BRL)</option>
//                 <option value="CNY">Chinese Yuan(CNY)</option>
//             </select>
//             <i class="fas fa-long-arrow-right fa-2x" style="margin-inline: 3%;"></i>
//             <label style="width: 18%">Target currency:</label>
//             <select class="form-control selectize curr-conv" id="target-new-${add_new_counter}" style="width: 15%; margin-left: -7px;">
//                 <option value="" selected disabled>Select Target Currency</option>
//                 <option value="USD">US dollar(USD)</option>
//                 <option value="EUR">Euro(EUR)</option>
//                 <option value="CHF">Swiss franc(CHF)</option>
//                 <option value="ARS">Argentine peso(ARS)</option>
//                 <option value="AUD">Australian dollar(AUD)</option>
//                 <option value="DKK">Danish krone(DKK)</option>
//                 <option value="CAD">Canadian dollar(CAD)</option>
//                 <option value="IDR">Indonesian rupiah(IDR)</option>
//                 <option value="JPY">Japanese yen(JPY)</option>
//                 <option value="KRW">Korea (South) Won(KRW)</option>
//                 <option value="NZD">New Zealand Dollars(NZD)</option>
//                 <option value="NOK">Norwegian krone(NOK)</option>
//                 <option value="RUR">Russian Ruble(RUR)</option>
//                 <option value="SAR">Saudi Riyal(SAR)</option>
//                 <option value="ZAR">South African Rand(ZAR)</option>
//                 <option value="SEK">Swedish krona(SEK)</option>
//                 <option value="TWD">New Taiwan dollar(TWD)</option>
//                 <option value="TRY">Turkish lira(TRY)</option>
//                 <option value="GBP">British pound(GBP)</option>
//                 <option value="MXN">Mexican peso(MXN)</option>
//                 <option value="MYR">Malaysian ringgit(MYR)</option>
//                 <option value="INR">Indian rupee(INR)</option>
//                 <option value="HKD">Hong Kong dollar(HKD)</option>
//                 <option value="BRL">Brazilian real(BRL)</option>
//                 <option value="CNY">Chinese Yuan(CNY)</option>
//             </select>
//         </div>
//         <div class="col-sm-12 sub-headings" id="cr-new-${add_new_counter}" style="display: flex;align-items: flex-end;margin-top: 1%;">
//             <label style="width: 20%">Conversion rate:</label>
//             <div class="col-sm-12" style="display: flex;" id="months-new-${add_new_counter}"></div>
//         </div>
//         <div class="form-group col-sm-12" id="hide-button-edit-new-${add_new_counter}" style="display: inline-flex; margin-top: 15px;margin-bottom: 0;">
//           <div style="margin-inline: 15px;">
//               <button class="btn btn-success add-conversion" type="button" id="add-new-${add_new_counter}">Add Conversion Rate</button>
//               <label id="add-currency-conv-${add_new_counter}"></label>
//           </div>
//           <div>
//               <button class="btn btn-default remove-new-cc" type="button" id="remove-new-${add_new_counter}">Cancel</button>
//           </div>
//       </div>
//       </div>
//     </div>
//   `);

//   last_12_months_cc.forEach(month => {
//     $(`#months-new-${add_new_counter}`).append(`
//       <div>
//         <div><label class="form-label">${month}</label></div>
//         <div><input type="number" min="0" class="curr-conv-${add_new_counter}" id="${add_new_counter}-${month.slice(0,3)}" style="width: 70%;"></div>
//       </div>
//     `)
//   });
// }