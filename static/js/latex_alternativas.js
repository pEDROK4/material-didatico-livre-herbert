// Renderiza LaTeX escrito entre cifrões nas alternativas: $x^2$ (na
// linha) e $$x^2$$ (em destaque). O texto vem sempre como texto puro
// (textContent), então nada aqui interpreta HTML.
(function () {
  const PADRAO = /\$\$([\s\S]+?)\$\$|\$([^$\n]+?)\$/g;

  window.renderizarLatex = function (elemento, texto) {
    if (texto === undefined) texto = elemento.dataset.latexOrigem || elemento.textContent;
    elemento.dataset.latexOrigem = texto;
    elemento.textContent = "";

    let ultimo = 0;
    let achado;
    PADRAO.lastIndex = 0;
    while ((achado = PADRAO.exec(texto)) !== null) {
      if (achado.index > ultimo) {
        elemento.appendChild(document.createTextNode(texto.slice(ultimo, achado.index)));
      }
      const display = achado[1] !== undefined;
      const span = document.createElement("span");
      try {
        katex.render(display ? achado[1] : achado[2], span, {
          throwOnError: false,
          displayMode: display,
        });
      } catch (erro) {
        span.textContent = achado[0];
      }
      elemento.appendChild(span);
      ultimo = achado.index + achado[0].length;
    }
    if (ultimo < texto.length) {
      elemento.appendChild(document.createTextNode(texto.slice(ultimo)));
    }
  };
})();
