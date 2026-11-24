from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("g/<str:code>/", views.index, name="game-page"),
    path("api/static/", views.static_info),
    path("api/games/", views.games),
    path("api/games/<str:code>/join/", views.join),
    path("api/games/<str:code>/leave/", views.leave),
    path("api/games/<str:code>/start/", views.start),
    path("api/games/<str:code>/add_bot/", views.add_bot),
    path("api/games/<str:code>/remove_seat/", views.remove_seat),
    path("api/games/<str:code>/state/", views.state),
    path("api/games/<str:code>/action/", views.action),
    path("api/games/<str:code>/hint/", views.hint),
]
