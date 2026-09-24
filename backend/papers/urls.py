from django.urls import path

from papers.views import StatsView

urlpatterns = [
    path("stats/", StatsView.as_view(), name="stats"),
]
