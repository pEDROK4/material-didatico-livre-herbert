from django.contrib.auth import views as auth_views
from django.urls import path
from django.views.generic import RedirectView

from questoes import views as questoes_views

from . import views

app_name = "core"

urlpatterns = [
    path("", views.raiz, name="raiz"),
    path("status/", views.status, name="status"),
    path("healthz/", views.healthz, name="healthz"),
    path("contato/", views.contato, name="contato"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="core/login.html", redirect_authenticated_user=True
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("trocar-senha/", views.trocar_senha, name="trocar_senha"),
    path("painel/", views.painel, name="painel"),
    # Menu lateral — todas apontando para o mesmo placeholder por
    # enquanto. Cada uma vira uma view própria quando for construída.
    path(
        "painel/questoes/adicionar/",
        questoes_views.adicionar_questao,
        name="questoes_adicionar",
    ),
    path(
        "painel/questoes/upload-imagem/",
        questoes_views.upload_imagem_editor,
        name="upload_imagem_editor",
    ),
    path(
        "painel/questoes/",
        questoes_views.listar_questoes,
        name="questoes_listar",
    ),
    path(
        "painel/cronograma/",
        views.cronograma,
        name="cronograma",
    ),
    path(
        "painel/estatisticas/",
        questoes_views.estatisticas,
        name="estatisticas",
    ),
    path(
        "painel/planejamento/",
        questoes_views.planejamento,
        name="planejamento",
    ),
    path(
        "painel/colaboradores/",
        views.colaboradores,
        name="colaboradores",
    ),
    path(
        "painel/avisos/",
        views.avisos,
        name="avisos",
    ),
    path(
        "painel/configuracoes/",
        views.configuracoes,
        name="configuracoes",
    ),
    # Endereço antigo da tela de professores (agora dentro de Configurações).
    path(
        "painel/professores/",
        RedirectView.as_view(pattern_name="core:configuracoes"),
    ),
    path(
        "painel/perfil/",
        views.perfil,
        name="perfil",
    ),
]
