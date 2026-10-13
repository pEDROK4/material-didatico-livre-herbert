import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Evento(models.Model):
    """
    Um evento do cronograma (prova, reunião, feriado, prazo etc). Só a
    coordenação (superusuário) cria, edita e apaga — os professores só
    enxergam o calendário.

    `data_fim` é opcional: em branco, o evento dura só o dia de `data`;
    preenchido, o evento aparece de forma contínua no calendário em
    todos os dias entre `data` e `data_fim` (inclusive).
    """

    titulo = models.CharField(max_length=150)
    descricao = models.TextField(blank=True)
    data = models.DateField()
    data_fim = models.DateField(
        null=True,
        blank=True,
        help_text="Deixe em branco para um evento de um dia só. Preencha para "
        "um evento que dura vários dias (ele aparece de forma contínua no calendário).",
    )
    hora = models.TimeField(null=True, blank=True)

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos_criados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["data", "hora"]
        verbose_name = "Evento"
        verbose_name_plural = "Eventos"

    def __str__(self):
        return f"{self.data:%d/%m/%Y} — {self.titulo}"

    def clean(self):
        if self.data_fim and self.data_fim < self.data:
            raise ValidationError(
                {"data_fim": "A data final não pode ser antes da data inicial."}
            )

    @property
    def ultimo_dia(self):
        return self.data_fim or self.data

    @property
    def dura_mais_de_um_dia(self):
        return bool(self.data_fim and self.data_fim > self.data)


def caminho_foto_perfil(instance, filename):
    # Uma foto por usuário — sobrescreve a anterior se a pessoa trocar,
    # em vez de acumular arquivo velho no storage.
    return f"perfis/{instance.usuario_id}/{filename}"


class PerfilProfessor(models.Model):
    """
    Dados de cada professor que vão compor o material didático impresso
    (não é o cadastro de acesso ao sistema — isso já existe no User).
    Cada usuário tem no máximo um perfil, criado automaticamente na
    primeira vez que a pessoa abre a tela "Ver perfil".
    """

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil"
    )
    nome_completo = models.CharField(max_length=150, blank=True)
    faculdade = models.CharField(
        max_length=150,
        blank=True,
        help_text="Instituição onde se formou ou está cursando.",
    )
    foto = models.ImageField(
        upload_to=caminho_foto_perfil,
        blank=True,
        null=True,
        help_text="Foto usada no material didático impresso.",
    )
    descricao = models.TextField(
        blank=True,
        help_text="Uma breve apresentação sua para o material.",
    )

    # Login por telefone: a coordenação preenche isso ao criar a conta
    # do professor (aqui no admin), e ele entra com esse número em vez
    # de um nome de usuário. Guardado só com dígitos (normalizado no
    # save()) pra "(11) 91234-5678" e "11912345678" caírem no mesmo
    # registro na hora do login.
    telefone = models.CharField(
        max_length=20,
        blank=True,
        unique=True,
        null=True,
        help_text="Só números, com DDD. É o que o professor usa pra entrar no sistema.",
    )
    senha_provisoria = models.BooleanField(
        default=False,
        help_text="Marque ao criar a conta com a senha genérica — a pessoa é "
        "obrigada a cadastrar uma senha nova assim que entrar pela primeira vez.",
    )

    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Perfil do professor"
        verbose_name_plural = "Perfis dos professores"

    def __str__(self):
        return self.nome_completo or self.usuario.get_username()

    def save(self, *args, **kwargs):
        # Normaliza pra só dígitos e, se não sobrar nada, guarda como
        # NULL (não string vazia) — senão duas pessoas sem telefone
        # cadastrado dariam choque na constraint de unicidade.
        self.telefone = re.sub(r"\D", "", self.telefone) or None if self.telefone else None
        super().save(*args, **kwargs)


class ConfiguracaoSistema(models.Model):
    """
    Configurações gerais do sistema que a coordenação liga/desliga pela
    tela "Configurações", sem precisar mexer no painel da hospedagem nem
    fazer deploy. Existe uma única linha (pk=1) — use `carregar()`.
    """

    manutencao_ativa = models.BooleanField(
        default=False,
        help_text="Com a manutenção ligada, só a coordenação usa o site; "
        "todos os outros veem a página de manutenção.",
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuração do sistema"
        verbose_name_plural = "Configurações do sistema"

    def __str__(self):
        return "Configurações do sistema"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def carregar(cls):
        configuracao, _ = cls.objects.get_or_create(pk=1)
        return configuracao


class Aviso(models.Model):
    """
    Pequeno recado da coordenação, mostrado no quadro "Informações" da
    página inicial. Só a coordenação (superusuário) cria e apaga.
    """

    titulo = models.CharField(max_length=80, blank=True)
    texto = models.TextField(max_length=500)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="avisos_criados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "Aviso"
        verbose_name_plural = "Avisos"

    def __str__(self):
        return self.titulo or self.texto[:40]
