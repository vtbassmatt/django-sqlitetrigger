from django.contrib import admin

from example.models import Book


class BookAdmin(admin.ModelAdmin):
    model = Book
    fields = ('title', 'pages', 'sheets')
    readonly_fields = ('sheets',)


# Register your models here.
admin.site.register(Book, BookAdmin)
