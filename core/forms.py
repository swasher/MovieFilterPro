from django import forms
from moviefilter.models import UserPreferences
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Submit, HTML, Field


class PreferencesForm(forms.ModelForm):
    class Meta:
        model = UserPreferences
        fields = ['last_scan', 'scan_from_page', 'plex_address', 'plex_token', 'countries', 'genres', 'max_year',
                  'min_rating', 'kinozal_domain', 'low_countries', 'low_genres', 'low_max_year', 'low_min_rating',
                  'tmdb_api_key', 'tmdb_v4_read_access_token', 'tmdb_v4_authenticated_access_token',
                  'ignore_title', 'cookie_pass', 'cookie_uid',
                  'torrents_hotfolder']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.label_class = 'col-sm-3'
        self.helper.field_class = 'col-md-9'
        # self.helper.add_input(Submit('submit', 'Save11'))

        self.fields["tmdb_v4_authenticated_access_token"].disabled = True
        self.fields["tmdb_v4_authenticated_access_token"].label = "Authenticated Write Access Token"

        self.helper.layout = Layout(
            HTML("""<h3>Last scan</h3><hr>"""),
            Field("last_scan"),
            Field("scan_from_page"),
            HTML("""<h3>Torrent</h3><hr>"""),
            Field("cookie_pass"),
            Field("cookie_uid"),
            Field("kinozal_domain"),
            Field("torrents_hotfolder"),
            HTML("""<h3>Plex</h3><hr>"""),
            Field("plex_address"),
            Field("plex_token"),
            HTML("""
                <h3>TMDB</h3>
                <i>v4_read_access_token берется с сайт, v4_authenticated_access_token клиет получает после аутентификации</i>
                <hr>
            """),
            Field("tmdb_api_key"),
            Field("tmdb_v4_read_access_token"),
            Field("tmdb_v4_authenticated_access_token"),
            HTML("""<h3>Strict rules</h3>
                <i>Сначала из всего списка удаляеся все, что содержит эти страны/жанры или менее года/рейтинга</i>
                <hr>
                """),
            Field("countries"),
            Field("genres"),
            Field("max_year"),
            Field("min_rating"),
            HTML("""
                <h3>Low priority</h3>
                <i>Оставшиеся фильмы помечаются как "Low priority", если они содержат указанные страны/жанры, или менее года/рейтинга</i>
                <hr>
            """),
            Field("low_countries"),
            Field("low_genres"),
            Field("low_max_year"),
            Field("low_min_rating"),
            HTML("""
                <h3>Ignore words from titles</h3>
                <i>Separete by comma</i>
                <hr>
            """),
            Field("ignore_title"),
            Submit("submit", "Save", css_class=""),
        )

    # def clean_zoom(self):
    #     zoom = int(self.cleaned_data["zoom"])
    #     if zoom < 70 or zoom > 130:
    #         raise ValidationError("Zoom not in range [70-130]!")
    #
    #     # Always return a value to use as the new cleaned data, even if
    #     # this method didn't change it.
    #     return zoom
