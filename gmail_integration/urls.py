from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('start-auth/', views.start_auth, name='start_auth'),
    path('oauth2callback/', views.oauth2callback, name='oauth2callback'),
    path('inbox/', views.inbox_view, name='inbox'),
    path('sent/', views.sent_view, name='sent'),
    path('thread/<str:thread_id>/', views.thread_view, name='thread_view'),
    path('email/<int:email_id>/', views.email_detail_view, name='email_detail'),
    path('sync/', views.force_sync_view, name='force_sync'),
    path('search/', views.search_emails, name='search_emails'),
    path('compose/', views.compose_email_view, name='compose_email'),
    path('attachments/<int:attachment_id>/download/', views.download_attachment, name='download_attachment'),
    path('test-error/', lambda request: views.render(request, 'gmail_integration/oauth_error.html', {'error_message': 'This is a test error message for preview purposes.'}), name='test_error'),
]
