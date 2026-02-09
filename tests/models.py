import sqlitetrigger
from django.db import models


class TestModel(models.Model):
    int_field = models.IntegerField(default=0)
    char_field = models.CharField(max_length=128, default="")
    float_field = models.FloatField(default=0.0)

    class Meta:
        app_label = "tests"


class ProtectedModel(models.Model):
    name = models.CharField(max_length=128, default="")

    class Meta:
        app_label = "tests"
        triggers = [
            sqlitetrigger.Protect(
                name="protect_deletes",
                operation=sqlitetrigger.Delete,
            ),
        ]


class ReadOnlyModel(models.Model):
    name = models.CharField(max_length=128, default="")
    created_at = models.CharField(max_length=128, default="now")

    class Meta:
        app_label = "tests"
        triggers = [
            sqlitetrigger.ReadOnly(
                name="readonly_created_at",
                fields=["created_at"],
            ),
        ]


class SoftDeleteModel(models.Model):
    name = models.CharField(max_length=128, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "tests"
        triggers = [
            sqlitetrigger.SoftDelete(
                name="soft_delete",
                field="is_active",
                value=False,
            ),
        ]


class FSMModel(models.Model):
    status = models.CharField(max_length=20, default="draft")

    class Meta:
        app_label = "tests"
        triggers = [
            sqlitetrigger.FSM(
                name="status_fsm",
                field="status",
                transitions=[
                    ("draft", "pending"),
                    ("pending", "completed"),
                    ("pending", "cancelled"),
                ],
            ),
        ]


class MultiOpProtectedModel(models.Model):
    name = models.CharField(max_length=128, default="")

    class Meta:
        app_label = "tests"
        triggers = [
            sqlitetrigger.Protect(
                name="protect_all",
                operation=sqlitetrigger.Update | sqlitetrigger.Delete,
            ),
        ]
