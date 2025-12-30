from django.db import models


class Country(models.Model):
    """Модель стран производства"""
    name = models.CharField('Название', max_length=100, unique=True)
    code = models.CharField('Код', max_length=2, unique=True, blank=True)

    class Meta:
        verbose_name = 'Страна'
        verbose_name_plural = 'Страны'
        ordering = ['name']

    def __str__(self):
        return self.name
