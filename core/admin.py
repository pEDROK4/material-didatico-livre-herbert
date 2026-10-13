from django.contrib import admin

from .models import Aviso, Evento, PerfilProfessor


@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = ["titulo", "data", "hora", "criado_por"]
    list_filter = ["data"]
    search_fields = ["titulo", "descricao"]
    date_hierarchy = "data"


@admin.register(PerfilProfessor)
class PerfilProfessorAdmin(admin.ModelAdmin):
    list_display = [
        "usuario",
        "nome_completo",
        "telefone",
        "senha_provisoria",
        "faculdade",
        "atualizado_em",
    ]
    list_filter = ["senha_provisoria"]
    search_fields = ["usuario__username", "nome_completo", "faculdade", "telefone"]
    autocomplete_fields = ["usuario"]


@admin.register(Aviso)
class AvisoAdmin(admin.ModelAdmin):
    list_display = ["__str__", "criado_por", "criado_em"]
