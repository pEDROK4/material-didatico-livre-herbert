from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import AssuntoForm
from .models import Alternativa, Assunto, Disciplina, Frente, Questao

Usuario = get_user_model()


class PlanejamentoTests(TestCase):
    """Edição, exclusão e substituição de aulas na tela de planejamento."""

    @classmethod
    def setUpTestData(cls):
        # As disciplinas/frentes vêm das migrações (dados semeados).
        cls.biologia_a = Frente.objects.get(disciplina__nome="Biologia", letra="A")
        cls.biologia_b = Frente.objects.get(disciplina__nome="Biologia", letra="B")
        cls.quimica_a = Frente.objects.get(disciplina__nome="Química", letra="A")
        cls.socio = Frente.objects.get(disciplina__nome="Sociologia/Filosofia", letra="A")

        cls.prof = Usuario.objects.create_user("prof", password="x")
        cls.biologia_a.professores.add(cls.prof)
        cls.biologia_b.professores.add(cls.prof)
        cls.coord = Usuario.objects.create_superuser("coord", password="x")

        cls.url = reverse("core:planejamento")

    def setUp(self):
        self.client.force_login(self.prof)

    def dados(self, **extra):
        base = {
            "disciplina": self.biologia_a.disciplina_id,
            "frente": self.biologia_a.pk,
            "nome": "Células",
            "descricao": "",
            "aula": 1,
        }
        base.update(extra)
        return base

    def criar_questao(self, assunto):
        autor = Usuario.objects.get(username="coord")
        questao = Questao.objects.create(assunto=assunto, enunciado="Q", autor=autor)
        Alternativa.objects.create(questao=questao, letra="A", texto="a", correta=True)
        return questao

    # --- cadastro e edição -------------------------------------------------

    def test_cadastro_simples(self):
        resposta = self.client.post(self.url, self.dados())
        self.assertRedirects(resposta, self.url)
        self.assertTrue(Assunto.objects.filter(frente=self.biologia_a, aula=1).exists())

    def test_get_com_editar_abre_modal_preenchido(self):
        assunto = Assunto.objects.create(frente=self.biologia_a, nome="Células", aula=3)
        resposta = self.client.get(self.url, {"editar": assunto.pk})
        self.assertContains(resposta, "Editar aula 3")
        self.assertContains(resposta, 'value="Células"')
        self.assertContains(resposta, "Excluir")

    def test_editar_atualiza_a_mesma_aula(self):
        assunto = Assunto.objects.create(frente=self.biologia_a, nome="Células", aula=3)
        self.client.post(
            self.url, self.dados(assunto_id=assunto.pk, nome="Citologia", aula=4)
        )
        assunto.refresh_from_db()
        self.assertEqual((assunto.nome, assunto.aula), ("Citologia", 4))
        self.assertEqual(Assunto.objects.count(), 1)

    def test_professor_nao_edita_aula_de_frente_que_nao_e_dele(self):
        alheio = Assunto.objects.create(frente=self.quimica_a, nome="Átomo", aula=1)
        self.assertEqual(self.client.get(self.url, {"editar": alheio.pk}).status_code, 404)
        resposta = self.client.post(
            self.url,
            self.dados(
                assunto_id=alheio.pk,
                disciplina=self.biologia_a.disciplina_id,
                nome="Invadido",
            ),
        )
        self.assertEqual(resposta.status_code, 404)
        alheio.refresh_from_db()
        self.assertEqual(alheio.nome, "Átomo")

    # --- exclusão ----------------------------------------------------------

    def test_excluir_aula_sem_questoes(self):
        assunto = Assunto.objects.create(frente=self.biologia_a, nome="Células", aula=3)
        resposta = self.client.post(self.url, {"acao": "excluir", "assunto_id": assunto.pk})
        self.assertRedirects(resposta, self.url)
        self.assertFalse(Assunto.objects.filter(pk=assunto.pk).exists())

    def test_nao_exclui_aula_com_questoes(self):
        assunto = Assunto.objects.create(frente=self.biologia_a, nome="Células", aula=3)
        self.criar_questao(assunto)
        self.client.post(self.url, {"acao": "excluir", "assunto_id": assunto.pk})
        self.assertTrue(Assunto.objects.filter(pk=assunto.pk).exists())

    def test_professor_nao_exclui_aula_de_outra_frente(self):
        alheio = Assunto.objects.create(frente=self.quimica_a, nome="Átomo", aula=1)
        resposta = self.client.post(self.url, {"acao": "excluir", "assunto_id": alheio.pk})
        self.assertEqual(resposta.status_code, 404)
        self.assertTrue(Assunto.objects.filter(pk=alheio.pk).exists())

    # --- número de aula repetido -------------------------------------------

    def test_numero_repetido_pede_confirmacao_e_nao_salva(self):
        antiga = Assunto.objects.create(frente=self.biologia_a, nome="Antiga", aula=2)
        resposta = self.client.post(self.url, self.dados(nome="Nova", aula=2))
        self.assertContains(resposta, "Já existe no seu planejamento uma aula de número 2")
        self.assertTrue(Assunto.objects.filter(pk=antiga.pk).exists())
        self.assertFalse(Assunto.objects.filter(nome="Nova").exists())

    def test_confirmando_a_antiga_e_apagada_e_a_nova_entra(self):
        antiga = Assunto.objects.create(frente=self.biologia_a, nome="Antiga", aula=2)
        self.client.post(
            self.url, self.dados(nome="Nova", aula=2, confirmar_substituicao="1")
        )
        self.assertFalse(Assunto.objects.filter(pk=antiga.pk).exists())
        self.assertEqual(Assunto.objects.get(frente=self.biologia_a, aula=2).nome, "Nova")

    def test_nao_substitui_aula_que_ja_tem_questoes(self):
        antiga = Assunto.objects.create(frente=self.biologia_a, nome="Antiga", aula=2)
        self.criar_questao(antiga)
        resposta = self.client.post(
            self.url, self.dados(nome="Nova", aula=2, confirmar_substituicao="1")
        )
        self.assertContains(resposta, "não pode ser substituída")
        self.assertTrue(Assunto.objects.filter(pk=antiga.pk).exists())
        self.assertFalse(Assunto.objects.filter(nome="Nova").exists())

    def test_mesmo_numero_em_outra_frente_nao_conflita(self):
        Assunto.objects.create(frente=self.biologia_b, nome="Outra", aula=2)
        self.client.post(self.url, self.dados(nome="Nova", aula=2))
        self.assertEqual(Assunto.objects.filter(aula=2).count(), 2)

    def test_editar_para_numero_ocupado_tambem_pede_confirmacao(self):
        Assunto.objects.create(frente=self.biologia_a, nome="Ocupante", aula=5)
        mover = Assunto.objects.create(frente=self.biologia_a, nome="Mover", aula=1)
        resposta = self.client.post(
            self.url, self.dados(assunto_id=mover.pk, nome="Mover", aula=5)
        )
        self.assertContains(resposta, "Já existe no seu planejamento uma aula de número 5")
        mover.refresh_from_db()
        self.assertEqual(mover.aula, 1)

    def test_salvar_a_propria_aula_sem_mudar_numero_nao_conflita(self):
        assunto = Assunto.objects.create(frente=self.biologia_a, nome="Células", aula=3)
        resposta = self.client.post(
            self.url, self.dados(assunto_id=assunto.pk, nome="Células 2", aula=3)
        )
        self.assertRedirects(resposta, self.url)
        self.assertEqual(Assunto.objects.count(), 1)


class AssuntoFormCascataTests(TestCase):
    def test_frente_precisa_pertencer_a_disciplina_escolhida(self):
        quimica_a = Frente.objects.get(disciplina__nome="Química", letra="A")
        biologia = Disciplina.objects.get(nome="Biologia")
        form = AssuntoForm(
            {"disciplina": biologia.pk, "frente": quimica_a.pk, "nome": "X", "aula": 1},
            usuario=Usuario.objects.create_superuser("c", password="x"),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("frente", form.errors)

    def test_limite_de_aulas_continua_valendo(self):
        socio = Frente.objects.get(disciplina__nome="Sociologia/Filosofia", letra="A")
        form = AssuntoForm(
            {"disciplina": socio.disciplina_id, "frente": socio.pk, "nome": "X", "aula": 20},
            usuario=Usuario.objects.create_superuser("c", password="x"),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("aula", form.errors)

    def test_opcoes_de_frente_trazem_disciplina_e_limite(self):
        form = AssuntoForm(usuario=Usuario.objects.create_superuser("c", password="x"))
        html = str(form["frente"])
        self.assertIn("data-disciplina", html)
        self.assertIn('data-limite-aula="15"', html)


class MatematicaBasicaTests(TestCase):
    def test_disciplina_propria_com_frente_unica_de_30_aulas(self):
        disciplina = Disciplina.objects.get(nome="Matemática Básica")
        frentes = list(disciplina.frentes.all())
        self.assertEqual(len(frentes), 1)
        self.assertEqual(frentes[0].limite_aula, 30)
        self.assertEqual(Disciplina.objects.get(nome="Matemática").frentes.count(), 2)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class EditarQuestaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        frente = Frente.objects.get(disciplina__nome="Biologia", letra="A")
        cls.assunto = Assunto.objects.create(frente=frente, nome="Células", aula=1)
        cls.autor = Usuario.objects.create_user("autor", password="x")
        cls.outro = Usuario.objects.create_user("outro", password="x")
        frente.professores.add(cls.autor, cls.outro)
        cls.coord = Usuario.objects.create_superuser("coord", password="x")
        cls.questao = Questao.objects.create(
            assunto=cls.assunto, enunciado="<p>Antigo</p>", autoria_propria=True, autor=cls.autor
        )
        Alternativa.objects.create(questao=cls.questao, letra="A", texto="um", correta=True)
        Alternativa.objects.create(questao=cls.questao, letra="B", texto="dois")
        cls.url = reverse("core:questoes_editar", args=[cls.questao.pk])

    def dados(self, **extra):
        base = {
            "assunto": self.assunto.pk,
            "enunciado": "<p>Novo</p>",
            "autoria_propria": "on",
            "alternativa_a": "$x^2$",
            "alternativa_b": "$$\\frac{a}{b}$$",
            "correta": "b",
        }
        base.update(extra)
        return base

    def test_autor_edita_enunciado_e_alternativas_com_latex(self):
        self.client.force_login(self.autor)
        self.assertContains(self.client.get(self.url), "um")
        resposta = self.client.post(self.url, self.dados())
        self.assertRedirects(resposta, reverse("core:questoes_listar"))
        self.questao.refresh_from_db()
        self.assertEqual(self.questao.enunciado, "<p>Novo</p>")
        alternativas = {a.letra: a for a in self.questao.alternativas.all()}
        self.assertEqual(alternativas["A"].texto, "$x^2$")
        self.assertTrue(alternativas["B"].correta)
        self.assertFalse(alternativas["A"].correta)

    def test_outro_professor_nao_edita(self):
        self.client.force_login(self.outro)
        self.client.post(self.url, self.dados())
        self.questao.refresh_from_db()
        self.assertEqual(self.questao.enunciado, "<p>Antigo</p>")

    def test_coordenacao_edita(self):
        self.client.force_login(self.coord)
        self.client.post(self.url, self.dados())
        self.questao.refresh_from_db()
        self.assertEqual(self.questao.enunciado, "<p>Novo</p>")


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class ExcluirQuestaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        frente = Frente.objects.get(disciplina__nome="Biologia", letra="A")
        cls.assunto = Assunto.objects.create(frente=frente, nome="Células", aula=1)
        cls.autor = Usuario.objects.create_user("autor", password="x")
        cls.outro = Usuario.objects.create_user("outro", password="x")
        cls.coord = Usuario.objects.create_superuser("coord", password="x")

    def setUp(self):
        self.questao = Questao.objects.create(
            assunto=self.assunto, enunciado="<p>Q</p>", autor=self.autor
        )
        Alternativa.objects.create(questao=self.questao, letra="A", texto="a", correta=True)
        self.url = reverse("core:questoes_excluir", args=[self.questao.pk])
        self.listagem = reverse("core:questoes_listar")

    def test_autor_exclui_e_alternativas_caem_junto(self):
        self.client.force_login(self.autor)
        resposta = self.client.post(self.url)
        self.assertRedirects(resposta, self.listagem)
        self.assertFalse(Questao.objects.filter(pk=self.questao.pk).exists())
        self.assertFalse(Alternativa.objects.filter(questao_id=self.questao.pk).exists())

    def test_coordenacao_exclui(self):
        self.client.force_login(self.coord)
        self.client.post(self.url)
        self.assertFalse(Questao.objects.filter(pk=self.questao.pk).exists())

    def test_outro_professor_nao_exclui(self):
        self.client.force_login(self.outro)
        self.client.post(self.url)
        self.assertTrue(Questao.objects.filter(pk=self.questao.pk).exists())

    def test_get_nao_exclui(self):
        self.client.force_login(self.autor)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 405)
        self.assertTrue(Questao.objects.filter(pk=self.questao.pk).exists())

    def test_anonimo_nao_exclui(self):
        self.client.post(self.url)
        self.assertTrue(Questao.objects.filter(pk=self.questao.pk).exists())

    def test_volta_para_a_listagem_com_os_filtros(self):
        self.client.force_login(self.autor)
        resposta = self.client.post(self.url, {"proximo": "?busca=abc&pagina=2"})
        self.assertRedirects(
            resposta, f"{self.listagem}?busca=abc&pagina=2", fetch_redirect_response=False
        )

    def test_botao_so_aparece_para_quem_pode(self):
        self.client.force_login(self.outro)
        self.assertNotContains(self.client.get(self.listagem), self.url)
        self.client.force_login(self.autor)
        self.assertContains(self.client.get(self.listagem), self.url)


class RenovarUrlsImagensTests(TestCase):
    """
    No Spaces a URL de upload é assinada e expira; ao exibir, o endereço
    das imagens do editor precisa ser refeito com assinatura nova.
    """

    def renovar(self, html):
        from unittest import mock

        from .templatetags.questoes_extras import renovar_urls_imagens

        with mock.patch(
            "questoes.templatetags.questoes_extras.default_storage.url",
            side_effect=lambda chave: f"https://novo.exemplo/{chave}?assinatura=NOVA",
        ):
            return renovar_urls_imagens(html)

    def test_url_assinada_expirada_do_spaces_e_refeita(self):
        antigo = (
            '<p>x</p><img src="https://bucket.nyc3.digitaloceanspaces.com/'
            'questoes/editor/abc123.png?X-Amz-Expires=3600&amp;X-Amz-Signature=velha">'
        )
        saida = self.renovar(antigo)
        self.assertIn("https://novo.exemplo/questoes/editor/abc123.png?assinatura=NOVA", saida)
        self.assertNotIn("velha", saida)

    def test_url_no_estilo_path_do_spaces_tambem(self):
        saida = self.renovar(
            '<img src="https://nyc3.digitaloceanspaces.com/meu-bucket/questoes/editor/x.jpg?a=1">'
        )
        self.assertIn("https://novo.exemplo/questoes/editor/x.jpg?assinatura=NOVA", saida)

    def test_url_local_media_continua_funcionando(self):
        saida = self.renovar('<img src="/media/questoes/editor/x.png">')
        self.assertIn("questoes/editor/x.png?assinatura=NOVA", saida)

    def test_imagem_de_outro_site_nao_e_mexida(self):
        html = '<img src="https://outro-site.com/questoes/editor/x.png">'
        self.assertEqual(self.renovar(html), html)

    def test_imagem_data_uri_nao_e_mexida(self):
        html = '<img src="data:image/png;base64,AAAA">'
        self.assertEqual(self.renovar(html), html)

    def test_html_sem_imagem_volta_igual(self):
        html = "<p>texto <strong>puro</strong></p>"
        self.assertEqual(self.renovar(html), html)
