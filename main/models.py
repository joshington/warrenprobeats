


from django.db import models
from django.db.models import Sum, Count, Avg
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from datetime import timedelta
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.http import HttpResponseForbidden, FileResponse
import os



class Genre(models.Model):
    """Model for beat genres"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    
    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']

class Album(models.Model):
    """Model for organizing beats by genre/collection"""
    title = models.CharField(max_length=200)
    genre = models.ForeignKey(Genre, on_delete=models.CASCADE, related_name='albums')
    description = models.TextField(blank=True)
    cover_image = models.FileField(upload_to='album_covers/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.title} - {self.genre.name}"

    class Meta:
        ordering = ['-created_at']

class Beat(models.Model):
    """Model for individual beats"""
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('reserved', 'Reserved - In Purchase Process'),
        ('sold', 'Sold'),
        ('downloaded', 'Downloaded'),
    ]
    
    title = models.CharField(max_length=200)
    album = models.ForeignKey(Album, on_delete=models.CASCADE, related_name='beats')
    description = models.TextField(blank=True)
    audio_file = models.FileField(upload_to='beats/')
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    duration = models.DurationField(help_text="Duration in seconds")
    bpm = models.PositiveIntegerField(help_text="Beats per minute")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    reserved_until = models.DateTimeField(null=True, blank=True)
    download_count = models.PositiveIntegerField(default=0) # Track number of downloads
    max_downloads = models.PositiveIntegerField(default=1, help_text="Maximum downloads allowed after purchase")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_favorite = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.title} - ${self.price}"

    #===now i ntend to mark the beat as downloaded
    def mark_as_downloaded(self):
        """Mark beat as downloaded and increment download count"""
        self.download_count += 1
        if self.download_count >= self.max_downloads:
            self.status = 'downloaded'
            self.is_available = False  
            # If you had this field, but you're using status
        self.save()
       
    #===mthd to check if beat is downloadable
    def is_downloadable(self):
        """Check if beat can still be downloaded"""
        return self.status in ['available', 'sold'] and self.download_count < self.max_downloads

    def reserve_for_purchase(self):
        """Reserve beat for 5 minutes during purchase process"""
        self.status = 'reserved'
        self.reserved_until = timezone.now() + timedelta(minutes=5)
        self.save()

    def complete_purchase(self):
        """Mark beat as sold after successful purchase"""
        self.status = 'sold'
        self.reserved_until = None
        self.save()

    def release_reservation(self):
        """Release reservation if purchase fails or times out"""
        if self.status == 'reserved' and self.reserved_until and self.reserved_until < timezone.now():
            self.status = 'available'
            self.reserved_until = None
            self.save()

    def is_available(self):
        """Check if beat is available for purchase"""
        self.release_reservation()  # Clean up expired reservations
        return self.status == 'available'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'reserved_until']),
            models.Index(fields=['album']),
        ]

class Buyer(models.Model):
    """Model for buyer information"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='buyer_profile')
    phone_number = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    country = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.user.email}"

    @property
    def email(self):
        return self.user.email

    @property
    def purchased_beats(self):
        """Get all beats purchased by this buyer"""
        return Beat.objects.filter(
            transactions__buyer=self,
            transactions__status='completed'
        ).distinct()

    class Meta:
        ordering = ['-created_at']

class Transaction(models.Model):
    """Model to record all transactions"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('stripe', 'Stripe'),
        ('paypal', 'PayPal'),
        ('bank_transfer', 'Bank Transfer'),
        ('other', 'Other'),
    ]
    
    buyer = models.ForeignKey(Buyer, on_delete=models.CASCADE, related_name='transactions')
    beat = models.ForeignKey(Beat, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    payment_reference = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"Transaction #{self.id} - {self.buyer.user.email} - ${self.amount}"

    def save(self, *args, **kwargs):
        """Override save to handle beat status updates"""
        if self.status == 'completed' and not self.completed_at:
            self.completed_at = timezone.now()
            self.beat.complete_purchase()
        elif self.status in ['failed', 'cancelled']:
            self.beat.release_reservation()
        
        super().save(*args, **kwargs)

    @classmethod
    def get_total_revenue(cls):
        """Get total revenue from all completed transactions"""
        return cls.objects.filter(status='completed').aggregate(
            total_revenue=Sum('amount')
        )['total_revenue'] or 0
    
    @classmethod
    def get_beats_sold_count(cls):
        """Get total number of beats sold (completed transactions)"""
        return cls.objects.filter(status='completed').count()
    
    @classmethod
    def get_daily_revenue(cls, days=30):
        """Get daily revenue for the last N days"""
        from django.db.models.functions import TruncDate
        return cls.objects.filter(
            status='completed',
            completed_at__gte=timezone.now() - timedelta(days=days)
        ).annotate(
            date=TruncDate('completed_at')
        ).values('date').annotate(
            daily_revenue=Sum('amount'),
            daily_sales=Count('id')
        ).order_by('-date')

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['buyer', 'status']),
            models.Index(fields=['beat', 'status']),
            models.Index(fields=['created_at']),
        ]


class RevenueReport(models.Model):
    """Model to store periodic revenue reports"""
    report_date = models.DateField(unique=True)
    total_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_beats_sold = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Revenue Report - {self.report_date} - ${self.total_revenue}"

    class Meta:
        ordering = ['-report_date']

# Utility functions for revenue tracking
def generate_daily_revenue_report():
    """Generate daily revenue report (can be run as a cron job)"""
    from datetime import date
    
    today = date.today()
    total_revenue = Transaction.get_total_revenue()
    total_beats_sold = Transaction.get_beats_sold_count()
    
    report, created = RevenueReport.objects.get_or_create(
        report_date=today,
        defaults={
            'total_revenue': total_revenue,
            'total_beats_sold': total_beats_sold
        }
    )
    
    if not created:
        report.total_revenue = total_revenue
        report.total_beats_sold = total_beats_sold
        report.save()
    
    return report

def get_revenue_statistics():
    """Get comprehensive revenue statistics"""
    completed_transactions = Transaction.objects.filter(status='completed')
    
    stats = {
        'total_revenue': completed_transactions.aggregate(
            total=Sum('amount')
        )['total'] or 0,
        'total_beats_sold': completed_transactions.count(),
        'average_sale_value': completed_transactions.aggregate(
            avg=Avg('amount')
        )['avg'] or 0,
        'today_revenue': completed_transactions.filter(
            completed_at__date=timezone.now().date()
        ).aggregate(total=Sum('amount'))['total'] or 0,
        'today_sales': completed_transactions.filter(
            completed_at__date=timezone.now().date()
        ).count(),
    }
    
    return stats

#=====mode to handle the download history=====
class DownloadHistory(models.Model):
    """Model for storing the download history"""
    beat = models.ForeignKey(Beat, on_delete=models.CASCADE, related_name='downloadhistory')
    buyer = models.ForeignKey(Buyer, on_delete=models.CASCADE, related_name='downloadhistory')
    downloaded_at = models.DateTimeField(auto_now_add=True)  # Track when downloaded

    def __str__(self):
        return  f"{self.beat.title} - {self.beat.download_count}"
    

    ##===i want to write a signal that after model is created, the download_count is incremented
    ##automatically, ofcourse i guess this has to be a post save_signal.

    class Meta:
        verbose_name_plural = "Download Histories"
        ordering = ['-downloaded_at']

#===signal to properly handle beat count
# Update the signal to properly handle beat download count
@receiver(post_save, sender=DownloadHistory)
def update_beat_download_count(sender, instance, created, **kwargs):
    if created:
        # Increment the beat's download count
        instance.beat.download_count += 1
        
        # If reached max downloads, mark as downloaded
        if instance.beat.download_count >= instance.beat.max_downloads:
            instance.beat.status = 'downloaded'
            
        instance.beat.save()

class Rating(models.Model):
    """Model for beat ratings"""
    beat = models.ForeignKey(Beat, on_delete=models.CASCADE, related_name='ratings')
    buyer = models.ForeignKey(Buyer, on_delete=models.CASCADE, related_name='ratings')
    rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Rating from 1 to 5 stars"
    )
    review = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.buyer.user.username} - {self.beat.title} - {self.rating} stars"

    class Meta:
        unique_together = ['beat', 'buyer']  # Prevent multiple ratings from same buyer
        ordering = ['-created_at']

# Signal to automatically create Buyer profile when User is created
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def create_buyer_profile(sender, instance, created, **kwargs):
    if created:
        Buyer.objects.get_or_create(user=instance)

@receiver(post_save, sender=User)
def save_buyer_profile(sender, instance, **kwargs):
    instance.buyer_profile.save()

#===signal to automatically increment the download count after the DownloadHistory model is created
@receiver(post_save, sender=DownloadHistory)
def auto_increment_download_count(sender, instance,created, **kwargs):
    if created:
        instance.download_count += 1


#=====everytime DownloadHistory Model is created, we need to increase the download count of the
#Beat Model.
