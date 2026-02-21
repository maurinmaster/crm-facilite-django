from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    path('export.xlsx', views.export_xlsx, name='export_xlsx'),

    path('clients/', views.clients_list, name='clients_list'),
    path('clients/new/', views.client_new, name='client_new'),
    path('clients/<str:client_id>/', views.client_detail, name='client_detail'),
    path('clients/<str:client_id>/edit/', views.client_edit, name='client_edit'),
    path('clients/<str:client_id>/delete/', views.client_delete, name='client_delete'),

    path('clients/<str:client_id>/contacts/new/', views.contact_new, name='contact_new'),
    path('contacts/<str:contact_id>/delete/', views.contact_delete, name='contact_delete'),

    path('clients/<str:client_id>/creds/new/', views.cred_new, name='cred_new'),
    path('creds/<str:cred_id>/delete/', views.cred_delete, name='cred_delete'),

    path('clients/<str:client_id>/links/new/', views.link_new, name='link_new'),
    path('links/<str:link_id>/delete/', views.link_delete, name='link_delete'),

    # Tarefas
    path('tasks/', views.tasks_dashboard, name='tasks_dashboard'),
    path('tasks/notifications/unread-count/', views.notifications_unread_count, name='notifications_unread_count'),
    path('tasks/notifications/', views.notifications_list, name='notifications_list'),
    path('tasks/notifications/read/', views.notifications_mark_read, name='notifications_mark_read_all'),
    path('tasks/notifications/read/<int:notification_id>/', views.notifications_mark_read, name='notifications_mark_read'),
    path('tasks/workload/', views.workload_dashboard, name='workload_dashboard'),
    path('tasks/settings/', views.tasks_settings, name='tasks_settings'),
    path('teams/settings/', views.teams_settings, name='teams_settings'),
    path('tasks/settings/stages/<int:stage_id>/delete/', views.task_stage_delete, name='task_stage_delete'),
    path('tasks/new/', views.task_new, name='task_new'),
    path('tasks/editor/upload-image/', views.task_editor_upload, name='task_editor_upload'),
    path('tasks/<int:task_id>/move/', views.task_move, name='task_move'),
    path('tasks/<int:task_id>/reorder/', views.task_reorder, name='task_reorder'),
    path('tasks/<int:task_id>/', views.task_detail, name='task_detail'),
]
