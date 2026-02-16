

from django.contrib import admin
from .models import Album, Beat, Genre, Buyer,Transaction,Rating, DownloadHistory



admin.site.register(Album)
admin.site.register(Beat)
admin.site.register(Genre)
admin.site.register(Buyer)
admin.site.register(Rating)

admin.site.register(DownloadHistory)

# Register your models here.
@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['id', 'buyer', 'beat', 'amount', 'status', 'payment_method', 'created_at']
    list_filter = ['status', 'payment_method', 'created_at']
    readonly_fields = ['created_at', 'updated_at', 'completed_at']
    
    def changelist_view(self, request, extra_context=None):
        # Add revenue stats to admin context
        extra_context = extra_context or {}
        extra_context['total_revenue'] = Transaction.get_total_revenue()
        extra_context['total_beats_sold'] = Transaction.get_beats_sold_count()
        return super().changelist_view(request, extra_context=extra_context)
