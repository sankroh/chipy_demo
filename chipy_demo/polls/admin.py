from chipy_demo.polls.models import Poll, Choice
from django.contrib import admin
import datetime

class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 3

class PollAdmin(admin.ModelAdmin):
    list_display = ('question', 'pub_date', 'was_published_today')
    fieldsets = [
        (None,               {'fields': ['question']}),
        ('Date information', {'fields': ['pub_date'], 'classes': ['collapse']}),
    ]
    inlines = [ChoiceInline]
    list_filter = ['pub_date']
    search_fields = ['question']
    date_hierarchy = 'pub_date'
    
    def was_published_today(self, obj):
        return obj.pub_date.date() == datetime.date.today()
    was_published_today.short_description = 'Published today?'
    

admin.site.register(Poll, PollAdmin)