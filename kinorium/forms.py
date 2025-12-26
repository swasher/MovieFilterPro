from django import forms


class UploadCsvForm(forms.Form):

    class Meta:
        fields = ['file1', 'file2']

    file_movie_list = forms.FileField()
    file_votes = forms.FileField()
