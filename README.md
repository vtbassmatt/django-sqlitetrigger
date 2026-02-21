# django-sqlitetrigger

SQLite trigger support integrated with Django models.

Inspired by [django-pgtrigger](https://github.com/AmbitionEng/django-pgtrigger), this package provides declarative trigger support for SQLite-backed Django projects. I'm very grateful for the existence of `django-pgtrigger`, without which I don't think this package could exist.

## AI disclosure

To be super clear: this project was built by prompting GitHub Copilot to modify `django-pgtrigger` for use with SQLite. I was in the process of doing something very similar manually, when it dawned on me that this is the ideal use for today's agentic AI coding systems.

The resulting package is usable by me for my purposes. As the license notes, it comes with no warranty or expectation that it'll solve your problems.

## Quick start

Install and add `sqlitetrigger` to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    "sqlitetrigger",
    # ...
]
```

Add triggers to your models:

```python
import sqlitetrigger

class ProtectedModel(models.Model):
    """This model cannot be deleted!"""

    class Meta:
        triggers = [
            sqlitetrigger.Protect(name="protect_deletes", operation=sqlitetrigger.Delete)
        ]
```

Install triggers:

```bash
python manage.py sqlitetrigger install
```

## Built-in triggers

- **Protect** — prevent insert, update, or delete operations
- **ReadOnly** — prevent changes to specific fields
- **SoftDelete** — intercept deletes and set a field instead
- **FSM** — enforce valid field state transitions

## Custom triggers

You can use the `Trigger` class directly.

```python
from sqlitetrigger import Trigger, After, Update, Func

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
```

See [the `Book` model in the example](example/models.py) to see it in action. The `Func` helper lets you refer to the model's database table and field names without hardcoding them.

## Running tests

```bash
uv run pytest
```
