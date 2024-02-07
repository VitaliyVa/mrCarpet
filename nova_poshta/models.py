from django.db import models


class SettlementType(models.Model):
    title = models.CharField(
        verbose_name="Тип населеного пункту", max_length=255, db_index=True
    )
    short_desc = models.CharField(
        verbose_name="Скорочено", max_length=255, null=True, blank=True
    )
    ref = models.CharField(verbose_name="Ref", max_length=255, null=True, blank=True)
    settlemnt_ref = models.CharField(
        verbose_name="Населений пункт", max_length=255, null=True, blank=True
    )

    def __str__(self) -> str:
        return f"{self.short_desc}"

    class Meta:
        verbose_name = "Тип населеного пункту"
        verbose_name_plural = "Типи населених пунктів"


class WarehouseType(models.Model):
    title = models.CharField(
        verbose_name="Тип відділення", max_length=255, db_index=True
    )
    ref = models.CharField(verbose_name="Ref", max_length=255, null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.title}"

    class Meta:
        verbose_name = "Тип відділення"
        verbose_name_plural = "Типи відділень"


class Area(models.Model):
    title = models.CharField(verbose_name="Область", max_length=255, db_index=True)
    ref = models.CharField(verbose_name="Ref", max_length=255, null=True, blank=True)

    def __str__(self):
        return f"{self.title} обл."

    class Meta:
        verbose_name = "Область"
        verbose_name_plural = "Області"


class Warehouse(models.Model):
    title = models.CharField(verbose_name="Відділення", max_length=255, db_index=True)
    short_address = models.CharField(
        verbose_name="Короткий адрес", max_length=255, db_index=True
    )
    ref = models.CharField(verbose_name="Ref", max_length=255, null=True, blank=True)
    type = models.ForeignKey(
        verbose_name="Тип відділення",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        to="nova_poshta.WarehouseType",
    )
    settlement = models.ForeignKey(
        verbose_name="Населений пункт",
        to="nova_poshta.Settlement",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    def __str__(self):
        return f"{self.title}"

    class Meta:
        verbose_name = "Відділення"
        verbose_name_plural = "Відділення"
        ordering = ["title"]


class Settlement(models.Model):
    title = models.CharField(
        verbose_name="Населений пункт", max_length=255, db_index=True
    )
    type = models.ForeignKey(
        verbose_name="Тип населеного пункту",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        to="nova_poshta.SettlementType",
    )
    ref = models.CharField(verbose_name="Ref", max_length=255, null=True, blank=True)
    area = models.ForeignKey(
        verbose_name="Область",
        to="nova_poshta.Area",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"{self.type} {self.title} {self.area}"

    class Meta:
        verbose_name = "Населений пункт"
        verbose_name_plural = "Населені пункти"
        ordering = ["title"]
