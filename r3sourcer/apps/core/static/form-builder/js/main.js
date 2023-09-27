var submitting = false;

function submitForm(form) {
    $('form .form-group').find('div.errors').remove();
    $('form .all-errors').addClass('hidden').find('li').remove();
    submitting = true;
    var formData = new FormData(form);
    formData.set('company', companyId);
    $.ajax({
        url: storageApiUrl,
        type: 'post',
        data: formData,
        contentType: false,
        processData: false,
        headers: {
            'X-CSRFToken': $('input[name=csrfmiddlewaretoken]').val()
        },
        success: function (response) {
            $(form).html('<div class="alert alert-success" role="alert">' + response.message + '</div>')
            submitting = false;
        },
        error: function (response) {
            for (var field in response.responseJSON) {
                var errorElem;
                var allErrorsContainer = $('form .all-errors');
                var errorsList = allErrorsContainer.find('ul');

                if (field === '__all__' || $('form .form-group.field-' + field).find('[name=' + field + ']').length === 0) {
                    response.responseJSON[field].map(function (error) {
                        $('<li/>', {
                            text: (field === '__all__' ? '' : field + ': ') + error,
                        }).appendTo(errorsList);
                    });
                    allErrorsContainer.removeClass('hidden');
                    continue
                }

                errorElem = $('form .form-group.field-' + field).find('div.errors');

                console.log(field, errorElem);

                if (errorElem.length === 0) {
                    console.log('added to', $('form .form-group.field-' + field));
                    errorElem = $('<div class="errors"></div>');
                    $('form .form-group.field-' + field).children('label').after(errorElem);
                }
                var errors = response.responseJSON[field].map(function (elem) {
                    return '<p class="label label-danger">' + elem + '</p>'
                }).join('');
                errorElem.html(errors);
            }
            submitting = true;
        }
    });
    return false;

}

jQuery(function ($) {
    var formRenderOpts = {
            dataType: 'json',
            formData: $('#form-builder').data('config')
        },
        renderedForm = $('<div>');
    renderedForm.formRender(formRenderOpts);
    var htmlForm = $(renderedForm.html());
    $(htmlForm).find('input[type=date]').attr({type: 'text'}).addClass('datapicker');
    $(htmlForm).find('select').each(function () {
        var elemName = $(this).attr('name');
        if (elemName.indexOf('[]') === elemName.length - 2)
            $(this).attr('name', elemName.split('').splice(0, elemName.length - 2).join(''));
    });
    $('#form-builder').html(htmlForm.html());
    $(".datapicker").datepicker();
    $('form').find('input[type=submit]').toggle(true);
});
