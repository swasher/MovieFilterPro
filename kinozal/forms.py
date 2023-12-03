from django import forms
from .models import UserPreferences
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Submit
from crispy_bootstrap5.bootstrap5 import FloatingField


class PreferencesForm(forms.ModelForm):
    normal_priority = forms.BooleanField(widget=forms.HiddenInput, initial=True)

    class Meta:
        model = UserPreferences
        fields = ['last_scan', 'countries', 'genres', 'max_year', 'min_rating']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.label_class = 'col-sm-3'
        self.helper.field_class = 'col-md-9'
        self.helper.add_input(Submit('submit', 'Save'))

    # def clean_zoom(self):
    #     zoom = int(self.cleaned_data["zoom"])
    #     if zoom < 70 or zoom > 130:
    #         raise ValidationError("Zoom not in range [70-130]!")
    #
    #     # Always return a value to use as the new cleaned data, even if
    #     # this method didn't change it.
    #     return zoom


class PreferencesFormLow(forms.ModelForm):
    low_priority = forms.BooleanField(widget=forms.HiddenInput, initial=True)

    class Meta:
        model = UserPreferences
        fields = ['low_countries', 'low_genres', 'low_max_year', 'low_min_rating']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.label_class = 'col-sm-3'
        self.helper.field_class = 'col-md-9'
        self.helper.add_input(Submit('submit', 'Save'))
