from django.db import models

from sqlitetrigger import Trigger, After, Update, Func

# Create your models here.
class Book(models.Model):
    class Meta:
        triggers = [
            Trigger(
                name='sheets_update',
                when=After,
                operation=Update,
                func=Func("UPDATE {meta.db_table} SET {columns.sheets} = ceil(new.{columns.pages} / 2.0) WHERE {columns.id} = new.{columns.id};"),
            )
        ]
    title = models.CharField(max_length=200)
    pages = models.PositiveIntegerField()
    sheets = models.PositiveIntegerField(editable=False)

    def __str__(self):
        return self.title
