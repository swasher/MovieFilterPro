from django import forms
from .models import UserPreferences
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Submit, HTML, Field
from crispy_bootstrap5.bootstrap5 import FloatingField


class PreferencesForm(forms.ModelForm):
    class Meta:
        model = UserPreferences
        fields = ['last_scan', 'scan_from_page', 'countries', 'genres', 'max_year', 'min_rating',
                  'low_countries', 'low_genres', 'low_max_year', 'low_min_rating']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.label_class = 'col-sm-3'
        self.helper.field_class = 'col-md-9'
        # self.helper.add_input(Submit('submit', 'Save11'))

        self.helper.layout = Layout(
            HTML("""
              <h3>Last scan</h3><hr>
              """),
            Field('last_scan'),
            Field('scan_from_page'),
            HTML("""<h3>Strict rules</h3><hr>
                <strong class='p-0'>Сначала из всего списка удаляеся все, что содержит эти страны/жанры или менее года/рейтинга</strong>
                """),
            Field('countries'),
            Field('genres'),
            Field('max_year'),
            Field('min_rating'),
            HTML("""
                <h3>Low priority</h3><hr>
                <strong>Оставшиеся фильмы помечаются как "Low priority", если они содержат указанные страны/жанры, или менее года/рейтинга</strong>
            """),
            Field('low_countries'),
            Field('low_genres'),
            Field('low_max_year'),
            Field('low_min_rating'),

            Submit('submit', 'Save!', css_class=''),
        )

    # def clean_zoom(self):
    #     zoom = int(self.cleaned_data["zoom"])
    #     if zoom < 70 or zoom > 130:
    #         raise ValidationError("Zoom not in range [70-130]!")
    #
    #     # Always return a value to use as the new cleaned data, even if
    #     # this method didn't change it.
    #     return zoom


class UploadCsvForm(forms.Form):

    class Meta:
        fields = ['file1', 'file2']

    file_movie_list = forms.FileField()
    file_votes = forms.FileField()
