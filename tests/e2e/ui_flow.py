"""Teste ponta a ponta da interface com Playwright (navegador de verdade).

    python tests/e2e/ui_flow.py http://localhost:5173
    python tests/e2e/ui_flow.py https://ifood-match.vercel.app

Fluxo A (desktop): demonstração -> Match -> "ver por que" -> 4 votos trocando de pessoa -> encerrar ->
reserva simulada -> avaliação -> recarregar a página e conferir que tudo persistiu.
Fluxo B (celular, 375 px): criar encontro -> convite -> preencher com IA -> salvar -> simular 2 participantes ->
gerar Match -> votar.
Capturas de tela vão para e2e-output/ (fora do Git).
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

OUT = Path(__file__).resolve().parents[2] / "e2e-output"
WAKE_TIMEOUT = 90_000  # o primeiro acesso ao Render gratuito pode levar ~1 min


class Report:
    def __init__(self):
        self.rows: list[tuple[bool, str, float]] = []
        self.t0 = time.perf_counter()

    def step(self, name: str):
        report = self

        class _Step:
            def __enter__(self):
                self.start = time.perf_counter()

            def __exit__(self, exc_type, exc, tb):
                ok = exc_type is None
                report.rows.append((ok, name + ("" if ok else f" -> {exc}"), time.perf_counter() - self.start))
                print(f"[{'OK ' if ok else 'FALHOU'}] {name} ({time.perf_counter() - self.start:.1f}s)", flush=True)
                if not ok:
                    print("      " + str(exc).strip().splitlines()[0][:300], flush=True)
                return False

        return _Step()


def shot(page: Page, name: str):
    OUT.mkdir(exist_ok=True)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)


def no_horizontal_scroll(page: Page):
    w = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    assert w[0] <= w[1] + 1, f"rolagem horizontal: {w[0]}px > {w[1]}px"


def switch_to(page: Page, index: int):
    page.select_option("select[aria-label='Trocar de participante']", index=index)
    page.wait_for_timeout(700)


def flow_demo(page: Page, base: str, r: Report):
    page.on("dialog", lambda d: d.accept())
    with r.step("A1. Página inicial abre e explica a proposta"):
        page.goto(base, timeout=WAKE_TIMEOUT)
        expect(page.get_by_role("heading", name=re.compile("Onde todo mundo"))).to_be_visible()
        expect(page.get_by_text("Protótipo de case")).to_be_visible()
        shot(page, "a1_inicio")
    with r.step("A2. Ver demonstração cria o grupo com 4 participantes prontos"):
        page.get_by_role("button", name="Ver demonstração").click()
        page.wait_for_url(re.compile(r"/g/.+/preferencias"), timeout=WAKE_TIMEOUT)
        expect(page.get_by_text("4 de 4 com preferências")).to_be_visible(timeout=WAKE_TIMEOUT)
        shot(page, "a2_preferencias_demo")
    with r.step("A3. Gerar Match mostra o top 3 com explicação e ponto de atenção"):
        page.get_by_role("button", name="Gerar Match").click()
        page.wait_for_url(re.compile(r"/match$"), timeout=WAKE_TIMEOUT)
        expect(page.get_by_text("Por que o iFood Match recomendou este restaurante?")).to_have_count(3, timeout=30_000)
        expect(page.locator("strong", has_text="Ponto de atenção:")).to_have_count(3)
        source = page.locator("text=/Explicação (gerada por IA|automática)/").first.inner_text()
        print(f"      fonte da explicação: {source}")
        page.get_by_role("button", name=re.compile("Ver por que")).first.click()
        expect(page.get_by_text("Score individual = 0,40·G")).to_be_visible()
        shot(page, "a3_match")
    with r.step("A4. Quatro votos trocando de participante na mesma aba"):
        page.get_by_role("link", name="Ir para a votação").click()
        page.wait_for_url(re.compile(r"/votacao$"))
        plan = [0, 0, 1, 2]  # Ana, Bruno -> 1ª; Carla -> 2ª; Davi -> 3ª
        for person, option in enumerate(plan):
            switch_to(page, person)
            page.get_by_role("button", name=re.compile("Votar aqui|Seu voto")).nth(option).click()
            page.wait_for_timeout(600)
        expect(page.get_by_text("4 de 4 votaram")).to_be_visible(timeout=10_000)
        shot(page, "a4_votacao")
    with r.step("A5. Encerrar a votação define o vencedor"):
        page.get_by_role("button", name=re.compile("Encerrar votação")).click()
        expect(page.get_by_text("Escolha concluída", exact=False).first).to_be_visible(timeout=15_000)
        expect(page.get_by_text(re.compile(r"venceu com 2 de 4 voto"))).to_be_visible()
    with r.step("A6. Reserva aparece claramente como simulada"):
        page.get_by_role("link", name="Ir para a reserva").click()
        page.get_by_role("button", name="Confirmar reserva simulada").click()
        expect(page.get_by_text("Reserva simulada", exact=True).first).to_be_visible(timeout=15_000)
        expect(page.get_by_text(re.compile(r"SIM-[0-9A-F]{6}"))).to_be_visible()
        expect(page.get_by_text("Nenhuma reserva real foi feita")).to_be_visible()
        shot(page, "a6_reserva")
    with r.step("A7. Avaliação de 1 a 5 com comentário"):
        page.get_by_role("radio", name="5 estrela(s)").click()
        page.get_by_placeholder("Comentário (opcional)").fill("Teste automático: deu tudo certo.")
        page.get_by_role("button", name="Enviar avaliação").click()
        expect(page.get_by_text("Avaliação registrada")).to_be_visible(timeout=15_000)
    with r.step("A8. Recarregar a página recupera tudo"):
        code = page.locator("text=/SIM-[0-9A-F]{6}/").first.inner_text()
        page.reload()
        expect(page.get_by_text("Reserva simulada", exact=True).first).to_be_visible(timeout=30_000)
        expect(page.get_by_text(code.strip())).to_be_visible()
        expect(page.get_by_text(re.compile(r"Média do grupo: 5"))).to_be_visible()
        shot(page, "a8_recarregado")


def flow_mobile(page: Page, base: str, r: Report):
    page.on("dialog", lambda d: d.accept())
    with r.step("B1. Criar encontro no celular gera código e link de convite"):
        page.goto(f"{base}/criar", timeout=WAKE_TIMEOUT)
        page.get_by_label("Seu apelido").fill("Teste")
        page.get_by_label("Quantas pessoas").fill("3")
        page.get_by_role("button", name="Criar e gerar convite").click()
        expect(page.get_by_text("Código de convite")).to_be_visible(timeout=WAKE_TIMEOUT)
        link = page.get_by_label("Link de convite").input_value()
        assert re.search(r"/entrar/[A-Z0-9]{8}$", link), link
        expect(page.get_by_role("link", name="Compartilhar no WhatsApp")).to_have_attribute("href", re.compile("wa.me"))
        no_horizontal_scroll(page)
        shot(page, "b1_convite_celular")
    with r.step("B2. Texto livre preenche o formulário (IA ou regras) e salva"):
        page.get_by_role("button", name="Preencher minhas preferências").click()
        page.get_by_label("Conte o que você quer (opcional)").fill(
            "Quero um lugar tranquilo, não muito caro, sou vegetariana e saio de Pinheiros")
        page.get_by_role("button", name="Preencher com IA").click()
        # "Vegetariana" existe como culinária e como restrição; basta que um chip tenha sido marcado.
        expect(page.locator("button[aria-pressed=true]", has_text="Vegetariana")).to_have_count(1, timeout=30_000)
        page.get_by_role("button", name="Salvar preferências").click()
        expect(page.get_by_text("✓ respondeu")).to_have_count(1, timeout=15_000)
        no_horizontal_scroll(page)
        shot(page, "b2_preferencias_celular")
    with r.step("B3. Simular dois participantes e gerar o Match"):
        for _ in range(2):
            page.get_by_role("button", name="+ Simular participante").click()
            expect(page.get_by_role("heading", name=re.compile("Preferências de Convidado"))).to_be_visible(timeout=15_000)
            page.get_by_role("button", name="Salvar preferências").click()
            page.wait_for_timeout(1200)
        expect(page.get_by_text("3 de 3 com preferências")).to_be_visible(timeout=15_000)
        page.get_by_role("button", name="Gerar Match").click()
        page.wait_for_url(re.compile(r"/match$"), timeout=WAKE_TIMEOUT)
        expect(page.get_by_text("Por que o iFood Match recomendou este restaurante?").first).to_be_visible(timeout=30_000)
        no_horizontal_scroll(page)
        shot(page, "b3_match_celular")


def main(base: str) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    base = base.rstrip("/")
    r = Report()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        desktop = browser.new_context(viewport={"width": 1280, "height": 900}, locale="pt-BR")
        try:
            flow_demo(desktop.new_page(), base, r)
        except Exception:
            pass
        mobile = browser.new_context(**p.devices["iPhone 13"], locale="pt-BR")
        try:
            flow_mobile(mobile.new_page(), base, r)
        except Exception:
            pass
        browser.close()
    ok = sum(1 for row in r.rows if row[0])
    print(f"\n{ok}/{len(r.rows)} etapas OK em {time.perf_counter() - r.t0:.0f}s. Capturas em {OUT}")
    return 0 if ok == len(r.rows) and len(r.rows) == 11 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5173"))
