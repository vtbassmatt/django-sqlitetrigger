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

## Running tests

```bash
uv run pytest
```
