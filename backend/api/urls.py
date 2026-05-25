from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TenantViewSet, PlantLookupViewSet, AirportLookupViewSet, EmissionFactorViewSet,
    IngestionJobViewSet, NormalizedActivityViewSet, IngestionUploadView,
    DashboardMetricsView, DBSeedingView, DBClearView
)

router = DefaultRouter()
router.register(r'tenants', TenantViewSet, basename='tenant')
router.register(r'plants', PlantLookupViewSet, basename='plant')
router.register(r'airports', AirportLookupViewSet, basename='airport')
router.register(r'factors', EmissionFactorViewSet, basename='factor')
router.register(r'jobs', IngestionJobViewSet, basename='job')
router.register(r'activities', NormalizedActivityViewSet, basename='activity')

urlpatterns = [
    path('', include(router.urls)),
    path('upload-source/', IngestionUploadView.as_view(), name='upload-source'),
    path('metrics/', DashboardMetricsView.as_view(), name='metrics'),
    path('seed-db/', DBSeedingView.as_view(), name='seed-db'),
    path('clear-db/', DBClearView.as_view(), name='clear-db'),
]
