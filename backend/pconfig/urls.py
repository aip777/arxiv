from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from basebox.views import HealthView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", HealthView.as_view(), name="health"),
    path("api/", include("papers.urls")),
    path("api/", include("rag.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

# Keep error responses JSON, like the rest of the API.
handler404 = "basebox.views.not_found"
handler500 = "basebox.views.server_error"
