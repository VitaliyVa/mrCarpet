from django.db import models


# Create your models here.
class City(models.Model):
    region_id = models.IntegerField()
    district_id = models.IntegerField()
    longitude = models.FloatField()
    city_type = models.CharField(max_length=550)
    status = models.CharField(max_length=550)
    region = models.CharField(max_length=550)
    city_id = models.IntegerField()
    district = models.CharField(max_length=550)
    city = models.CharField(max_length=550)

    class Meta:
        verbose_name = "Населений пункт"
        verbose_name_plural = "Населені пункти"

    def __str__(self):
        return f"{self.city_type[0]}. {self.city} ({self.region} обл. {self.district} р-н.)"


class UkrOffice(models.Model):
    related_city = models.ForeignKey(
        verbose_name="Населений пункт",
        to=City,
        on_delete=models.CASCADE,
        related_name="related_city"
    )
    post_office = models.CharField(max_length=550)
    post_code = models.IntegerField()
    longitude = models.FloatField()
    street = models.CharField(max_length=550)
    post_office_id = models.IntegerField()
    status = models.CharField(max_length=550)
    type = models.CharField(max_length=550)

    class Meta:
        verbose_name = "Офіс"
        verbose_name_plural = "Офіси"

    def __str__(self):
        return self.post_office
