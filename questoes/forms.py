from django import forms
from django.db import transaction
from django.db.models import Q

from .models import Alternativa, Assunto, Disciplina, Frente, Questao
from .sanitizacao import enunciado_esta_vazio, sanitizar_html_enunciado


class SelectFrente(forms.Select):
    """
    Select de frente que carrega, em cada <option>, a disciplina a que
    ela pertence e o limite de aulas dela (15 para Sociologia/Filosofia
    e Português, 30 para as demais). O JS do modal usa esses atributos
    para filtrar as frentes pela disciplina escolhida e para restringir
    o campo "aula", tudo na hora, sem round-trip ao servidor.
    """

    def __init__(self, *args, dados=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.dados = dados or {}

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        dados = self.dados.get(str(value))
        if dados:
            option["attrs"]["data-limite-aula"] = dados["limite"]
            option["attrs"]["data-disciplina"] = dados["disciplina"]
        return option


class AssuntoForm(forms.ModelForm):
    """
    Formulário de cadastro/edição de um conteúdo (assunto). Duas
    "cascatas": primeiro se escolhe a Disciplina, depois a Frente (o JS
    do modal só mostra as frentes da disciplina escolhida).

    Os dois dropdowns só listam o que o professor logado pode usar — e
    isso também vale como validação no backend: se alguém forjar o POST
    com o pk de uma frente que não é dele, o ModelChoiceField rejeita,
    porque o valor não está no queryset permitido (veja `usuario` no
    __init__). A disciplina é só auxiliar (não é salva): o clean()
    confere que a frente pertence a ela.
    """

    field_order = ["disciplina", "frente", "nome", "descricao", "aula"]

    disciplina = forms.ModelChoiceField(
        queryset=Disciplina.objects.none(),
        label="Disciplina",
        empty_label=None,
    )
    frente = forms.ModelChoiceField(
        queryset=Frente.objects.none(),
        label="Frente",
    )

    class Meta:
        model = Assunto
        fields = ["frente", "nome", "descricao", "aula"]
        labels = {
            "nome": "Nome do assunto",
            "descricao": "Descrição do assunto",
            "aula": "Aula",
        }
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)

        frentes = Frente.objects.select_related("disciplina")
        if usuario is not None and not usuario.is_superuser:
            frentes = frentes.filter(professores=usuario)
        frentes = frentes.order_by("disciplina__nome", "letra")
        self.fields["frente"].queryset = frentes
        self.fields["disciplina"].queryset = Disciplina.objects.filter(
            frentes__in=frentes
        ).distinct().order_by("nome")

        # Troca o widget pelo que carrega disciplina/limite por opção,
        # antes de definir as choices — o setter de `choices` também
        # propaga a lista pro widget atual.
        dados = {
            str(frente.pk): {
                "limite": frente.limite_aula,
                "disciplina": frente.disciplina_id,
            }
            for frente in frentes
        }
        self.fields["frente"].widget = SelectFrente(dados=dados)
        self.fields["frente"].choices = [(frente.pk, frente.nome) for frente in frentes]

        # Editando: já abre com a disciplina da aula selecionada.
        if self.instance.pk:
            self.initial["disciplina"] = self.instance.frente.disciplina_id

    def clean(self):
        dados = super().clean()
        disciplina = dados.get("disciplina")
        frente = dados.get("frente")
        aula = dados.get("aula")
        if disciplina is not None and frente is not None and frente.disciplina_id != disciplina.pk:
            self.add_error("frente", "Essa frente não pertence à disciplina escolhida.")
        elif frente is not None and aula is not None and aula > frente.limite_aula:
            self.add_error(
                "aula",
                f"{frente.disciplina.nome} só vai até a aula {frente.limite_aula}.",
            )
        return dados


LETRAS_ALTERNATIVAS = ["a", "b", "c", "d", "e"]


class QuestaoForm(forms.ModelForm):
    """
    Formulário de cadastro de questão. Junta num só form: a escolha do
    assunto (restrita ao que o professor pode usar, igual ao
    AssuntoForm), o enunciado rico (vem do editor Quill como HTML
    escondido num campo hidden, sanitizado em clean_enunciado), a
    origem (vestibular ou autoria própria) e até 5 alternativas com
    rádio marcando a correta — em vez de um formset, que exigiria
    gerenciar management form e não dá pra impor "só uma marcada como
    certa" com naturalidade.

    Com `instance`, edita uma questão existente: as alternativas são
    regravadas por inteiro. O texto das alternativas aceita LaTeX entre
    cifrões ($x^2$), renderizado com KaTeX na exibição.
    """

    assunto = forms.ModelChoiceField(
        queryset=Assunto.objects.none(),
        label="Assunto",
    )
    enunciado = forms.CharField(widget=forms.HiddenInput(), required=True)

    alternativa_a = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}), label="Alternativa A"
    )
    alternativa_b = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}), label="Alternativa B"
    )
    alternativa_c = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}), label="Alternativa C", required=False
    )
    alternativa_d = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}), label="Alternativa D", required=False
    )
    alternativa_e = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}), label="Alternativa E", required=False
    )
    correta = forms.ChoiceField(
        choices=[("a", "A"), ("b", "B"), ("c", "C"), ("d", "D"), ("e", "E")],
        widget=forms.RadioSelect,
        label="Qual é a alternativa correta",
    )

    class Meta:
        model = Questao
        fields = [
            "assunto",
            "enunciado",
            "autoria_propria",
            "banca",
            "ano",
            "prova",
        ]
        labels = {
            "autoria_propria": "Questão de autoria própria (não é de vestibular)",
            "banca": "Banca",
            "ano": "Ano",
            "prova": "Prova",
        }
        widgets = {
            "autoria_propria": forms.CheckboxInput(),
            "ano": forms.NumberInput(attrs={"min": 1990, "max": 2100}),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["autoria_propria"].required = False

        queryset = Assunto.objects.select_related(
            "frente", "frente__disciplina"
        ).order_by("frente__disciplina__nome", "frente__letra", "aula", "nome")
        if usuario is not None and not usuario.is_superuser:
            filtro = Q(frente__professores=usuario)
            # Editando: o assunto atual continua válido mesmo que a
            # frente tenha sido retirada do professor depois.
            if self.instance.pk:
                filtro |= Q(pk=self.instance.assunto_id)
            queryset = queryset.filter(filtro).distinct()
        self.fields["assunto"].queryset = queryset

        # Optgroup por "Disciplina — Frente", pra ficar claro de qual
        # frente é cada assunto quando o professor tem mais de uma.
        agrupado = {}
        for assunto in queryset:
            rotulo_grupo = f"{assunto.frente.disciplina.nome} — {assunto.frente.nome}"
            agrupado.setdefault(rotulo_grupo, []).append(
                (assunto.pk, f"Aula {assunto.aula} — {assunto.nome}")
            )
        self.fields["assunto"].choices = [
            (grupo, opcoes) for grupo, opcoes in agrupado.items()
        ]

        # Editando: preenche alternativas e a correta a partir do banco.
        if self.instance.pk and not self.is_bound:
            for alternativa in self.instance.alternativas.all():
                letra = alternativa.letra.lower()
                self.initial[f"alternativa_{letra}"] = alternativa.texto
                if alternativa.correta:
                    self.initial["correta"] = letra

    def clean_enunciado(self):
        html_limpo = sanitizar_html_enunciado(self.cleaned_data.get("enunciado", ""))
        if enunciado_esta_vazio(html_limpo):
            raise forms.ValidationError("Escreva o enunciado da questão.")
        return html_limpo

    def clean(self):
        dados = super().clean()

        preenchidas = {}
        for letra in LETRAS_ALTERNATIVAS:
            texto = (dados.get(f"alternativa_{letra}") or "").strip()
            if texto:
                preenchidas[letra] = texto

        if len(preenchidas) < 2:
            self.add_error(None, "Cadastre pelo menos duas alternativas.")

        correta = dados.get("correta")
        if correta and preenchidas and correta not in preenchidas:
            self.add_error(
                "correta", "A alternativa marcada como correta precisa estar preenchida."
            )

        if dados.get("autoria_propria"):
            dados["banca"] = ""
            dados["ano"] = None
            dados["prova"] = ""

        self._alternativas_preenchidas = preenchidas
        return dados

    def save(self, commit=True, autor=None):
        questao = super().save(commit=False)
        if autor is not None:
            questao.autor = autor
        if commit:
            with transaction.atomic():
                questao.save()
                self._salvar_alternativas(questao)
        return questao

    def _salvar_alternativas(self, questao):
        correta = self.cleaned_data["correta"]
        questao.alternativas.all().delete()
        Alternativa.objects.bulk_create(
            Alternativa(
                questao=questao,
                letra=letra.upper(),
                texto=texto,
                correta=(letra == correta),
            )
            for letra, texto in self._alternativas_preenchidas.items()
        )
