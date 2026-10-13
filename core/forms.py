from django import forms

from .models import Aviso, Evento, PerfilProfessor


class EventoForm(forms.ModelForm):
    class Meta:
        model = Evento
        fields = ["titulo", "data", "data_fim", "hora", "descricao"]
        labels = {
            "titulo": "Título",
            "data": "Data (início)",
            "data_fim": "Data final (opcional)",
            "hora": "Hora (opcional)",
            "descricao": "Descrição",
        }
        help_texts = {
            "data_fim": "Só preencha se o evento durar mais de um dia.",
        }
        widgets = {
            # format="%Y-%m-%d"/"%H:%M" é obrigatório aqui: sem isso, o
            # Django preenche o valor no formato localizado (pt-br,
            # "28/09/2026"), que o <input type="date"> do navegador não
            # reconhece — e o campo aparece em branco ao editar.
            "data": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "data_fim": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "hora": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "descricao": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        dados = super().clean()
        data = dados.get("data")
        data_fim = dados.get("data_fim")
        if data and data_fim and data_fim < data:
            self.add_error("data_fim", "A data final não pode ser antes da data inicial.")
        return dados


class PerfilForm(forms.ModelForm):
    class Meta:
        model = PerfilProfessor
        fields = ["nome_completo", "faculdade", "foto", "descricao"]
        labels = {
            "nome_completo": "Nome completo",
            "faculdade": "Faculdade",
            "foto": "Foto para o material",
            "descricao": "Descrição pessoal",
        }
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 4}),
        }


class AvisoForm(forms.ModelForm):
    class Meta:
        model = Aviso
        fields = ["titulo", "texto"]
        labels = {"titulo": "Título (opcional)", "texto": "Aviso"}
        widgets = {
            "titulo": forms.TextInput(attrs={"maxlength": 80}),
            "texto": forms.Textarea(attrs={"rows": 3, "maxlength": 500}),
        }
