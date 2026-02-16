from django.urls import include,path, re_path as url
from . import views
from main.views import payment_response



app_name = 'main'

urlpatterns = [
    url(r'^$', views.index, name='index'),
    url(r'^(?P<album_id>[0-9]+)/$', views.detail, name='detail'),
    url(r'^(?P<beat_id>[0-9]+)/favorite/$', views.favorite, name='favorite'),
    url(r'^(?P<album_id>[0-9]+)/favorite_album/$', views.favorite_album, name='favorite_album'),
    path('callback', payment_response, name='payment_response'),
    path('purch_download/<int:beat_id>/', views.purchase_and_download_beat, name='purch_download'),
]