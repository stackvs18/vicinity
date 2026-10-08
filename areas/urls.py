from django.urls import path

from areas import api, views

urlpatterns = [
    # Pages
    path("", views.home, name="home"),
    path("search/", views.search, name="search"),
    path("locate/", views.locate, name="locate"),
    path("area/<int:pk>/", views.area_detail, name="area_detail"),
    path("area/<int:pk>/save/", views.toggle_save, name="toggle_save"),
    path("compare/", views.compare, name="compare"),
    path("saved/", views.saved_areas, name="saved_areas"),
    path("signup/", views.signup, name="signup"),
    path("health/", views.health, name="health"),

    # REST API
    path("api/score/", api.ScoreView.as_view(), name="api_score"),
    path("api/suggest/", api.SuggestView.as_view(), name="api_suggest"),
    path("api/areas/", api.AreaListView.as_view(), name="api_area_list"),
    path("api/areas/<int:pk>/", api.AreaDetailView.as_view(), name="api_area_detail"),
]
