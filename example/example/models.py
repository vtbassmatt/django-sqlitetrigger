from django.db import models

from sqlitetrigger import Trigger, After, Update

# Create your models here.
class Book(models.Model):
    class Meta:
        triggers = [
            Trigger(
                name='sheets_update',
                when=After,
                operation=Update,
                func="UPDATE example_book SET sheets = new.pages / 2 WHERE id = new.id;",
            )
        ]
    title = models.CharField(max_length=200)
    pages = models.PositiveIntegerField()
    sheets = models.PositiveIntegerField(editable=False)

    def __str__(self):
        return self.title
