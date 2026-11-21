"""Gera data/restaurants_seed.json com 50 restaurantes 100% fictícios em São Paulo.

Nomes e descrições foram escritos à mão para não lembrar estabelecimentos reais.
Coordenadas, horários, avaliação e disponibilidade são sintéticos e determinísticos
(semente fixa), então rodar de novo gera exatamente o mesmo arquivo.

Uso:  python data/generate_seed.py
"""
from __future__ import annotations

import json
import math
import random
import uuid
from pathlib import Path

HERE = Path(__file__).parent
REF = json.loads((HERE / "reference.json").read_text(encoding="utf-8"))
NAMESPACE = uuid.UUID("6f1c2a52-6d0e-4a8e-9a43-1f0b8c1d2e33")

V, VG, SG, SL = "vegetariana", "vegana", "sem_gluten", "sem_lactose"

# (nome, culinária, bairro, preço médio/pessoa, opções alimentares, ambientes,
#  capacidade máx. de grupo, aceita reserva, perfil de horário, descrição)
RESTAURANTS = [
    ("Cantina Vento Leste", "italiana", "Pinheiros", 85, [V, SL], ["tranquilo", "romantico"], 30, True, "padrao",
     "Massas frescas feitas na casa e molhos de cozimento lento, em salão de luz baixa."),
    ("Trattoria Lume Antico", "italiana", "Vila Madalena", 72, [V], ["casual", "animado"], 40, True, "padrao",
     "Cantina de mesas compridas, boa para grupos, com risotos e pratos para dividir."),
    ("Osteria Pedra Branca", "italiana", "Jardins", 165, [V, SG], ["romantico", "tranquilo"], 24, True, "jantar",
     "Menu degustação de inspiração toscana e carta de vinhos enxuta."),
    ("Forno Quintal Nove", "pizzaria", "Perdizes", 58, [V, VG, SG], ["casual", "ao_ar_livre"], 50, True, "noite",
     "Pizza de fermentação longa num quintal coberto; tem massa sem glúten e queijo vegetal."),
    ("Pizzaria Lua de Tijolo", "pizzaria", "Mooca", 49, [V], ["casual", "animado"], 60, False, "noite",
     "Pizza de forno a lenha em salão barulhento e familiar."),
    ("Massa Madre Estelar", "pizzaria", "Butantã", 64, [V, VG, SG, SL], ["casual", "tranquilo"], 40, True, "noite",
     "Pizzas de longa fermentação com cardápio inteiro adaptável para restrições."),
    ("Maré Calma Sushi", "japonesa", "Liberdade", 95, [V, SG, SL], ["tranquilo"], 24, True, "padrao",
     "Balcão de sushi tradicional, opções de shoyu sem glúten e combinados vegetarianos."),
    ("Omakase Kumo Azul", "japonesa", "Itaim Bibi", 240, [SL], ["tranquilo", "romantico"], 10, True, "jantar",
     "Omakase de doze etapas para poucos lugares no balcão."),
    ("Lamen Ponte Vermelha", "japonesa", "Liberdade", 55, [V], ["casual", "animado"], 20, False, "padrao",
     "Lamen de caldo encorpado servido rápido; tem versão vegetariana com missô."),
    ("Izakaya Lanterna Torta", "japonesa", "Vila Madalena", 88, [V, SL], ["animado"], 30, True, "bar",
     "Petiscos japoneses grelhados e drinques, clima de bar até tarde."),
    ("Casa Jacarandá", "brasileira", "Pinheiros", 68, [V, SG], ["casual", "ao_ar_livre"], 45, True, "padrao",
     "Comida brasileira de fazenda com varanda arborizada e pratos para compartilhar."),
    ("Panela de Barro Fumê", "brasileira", "Vila Mariana", 45, [V, SG, SL], ["casual"], 35, True, "padrao",
     "Pratos feitos caseiros e moquecas de panela de barro, com opções sem glúten."),
    ("Boteco Esquina do Ipê", "brasileira", "Vila Madalena", 52, [V], ["animado", "ao_ar_livre"], 70, False, "bar",
     "Boteco de calçada com porções, petiscos vegetarianos e música ao vivo."),
    ("Fogão de Lenha Serra Fina", "brasileira", "Butantã", 58, [V, SG], ["casual"], 60, True, "padrao",
     "Cozinha mineira de fogão a lenha, servida em travessas para a mesa."),
    ("Varal de Temperos", "brasileira", "Brooklin", 74, [V, VG, SG, SL], ["casual", "ao_ar_livre"], 40, True, "padrao",
     "Cozinha brasileira contemporânea com horta própria e cardápio inclusivo."),
    ("Sertão Lilás", "nordestina", "Bela Vista", 62, [V, SG], ["casual", "animado"], 50, True, "padrao",
     "Baião de dois, carne de sol e tapiocas, com forró ao vivo às sextas."),
    ("Mandacaru Azul", "nordestina", "Santana", 48, [V, SG, SL], ["casual"], 40, True, "padrao",
     "Comida nordestina caseira com cuscuz, macaxeira e opções vegetarianas."),
    ("Horta Viva Cozinha", "vegetariana", "Vila Mariana", 55, [V, VG, SG, SL], ["tranquilo", "casual"], 30, True, "padrao",
     "Cozinha 100% vegetal, com cardápio sem glúten e sem lactose."),
    ("Folha & Brasa", "vegetariana", "Pinheiros", 78, [V, VG, SG, SL], ["tranquilo", "romantico"], 28, True, "jantar",
     "Vegetais na brasa e menu autoral vegetariano em ambiente intimista."),
    ("Raiz Urbana Vegana", "vegetariana", "Consolação", 46, [V, VG, SL], ["casual"], 32, False, "padrao",
     "Hambúrgueres de grão, bowls e sobremesas veganas a preço justo."),
    ("Dragão de Papel", "chinesa", "Liberdade", 52, [V, SL], ["casual", "animado"], 60, True, "padrao",
     "Dim sum e pratos de wok em mesas redondas giratórias para grupos."),
    ("Jardim de Jade", "chinesa", "Tatuapé", 66, [V, SG, SL], ["tranquilo"], 40, True, "padrao",
     "Cozinha cantonesa leve, com molhos sem glúten sob pedido."),
    ("Wok Vento Norte", "chinesa", "Brooklin", 47, [V, VG, SL], ["casual"], 30, False, "padrao",
     "Yakissoba e arroz frito montados na hora, com proteína vegetal."),
    ("Seul Noturno", "coreana", "Bela Vista", 82, [V, SL], ["animado"], 36, True, "bar",
     "Churrasco coreano na mesa, banchan variados e soju."),
    ("Kimchi Quintal", "coreana", "Liberdade", 64, [V, VG, SL], ["casual"], 24, True, "padrao",
     "Bibimbap, tteokbokki e kimchi da casa, com versões veganas."),
    ("Lótus Picante", "tailandesa", "Itaim Bibi", 98, [V, VG, SG, SL], ["tranquilo", "romantico"], 30, True, "padrao",
     "Curries tailandeses à base de leite de coco, quase todo o cardápio sem glúten."),
    ("Manjericão Sagrado", "tailandesa", "Vila Madalena", 74, [V, SG, SL], ["casual"], 26, True, "padrao",
     "Pad thai, saladas picantes e curries em salão pequeno e colorido."),
    ("Especiaria Monção", "indiana", "Pinheiros", 80, [V, VG, SG], ["tranquilo"], 34, True, "padrao",
     "Thalis do sul da Índia e curries vegetarianos com pão feito no tandoor."),
    ("Curry do Viajante", "indiana", "Bela Vista", 58, [V, VG, SG, SL], ["casual"], 28, True, "padrao",
     "Curries do dia servidos em pratos executivos, muitos veganos."),
    ("Cedro & Mel", "arabe", "Consolação", 44, [V, VG, SL], ["casual", "animado"], 60, True, "padrao",
     "Mezze para dividir, falafel e kafta, em salão grande e movimentado."),
    ("Tenda do Zaatar", "arabe", "Moema", 62, [V, SG], ["tranquilo", "ao_ar_livre"], 40, True, "padrao",
     "Grelhados e pastas árabes servidos em pátio com tendas."),
    ("Esfiharia Areia Dourada", "arabe", "Santana", 36, [V], ["casual"], 50, False, "padrao",
     "Esfihas abertas e fechadas assadas na hora, boa pedida para orçamento curto."),
    ("Cantina Nopal", "mexicana", "Pinheiros", 66, [V, VG, SG, SL], ["animado", "ao_ar_livre"], 45, True, "bar",
     "Tacos de tortilha de milho (sem glúten), guacamole e terraço animado."),
    ("Taqueria Calavera Verde", "mexicana", "Vila Madalena", 54, [V, SG], ["animado"], 35, False, "bar",
     "Tacos, quesadillas e nachos, com música alta e clima de festa."),
    ("Cevicheria Pacífico Sul", "peruana", "Itaim Bibi", 135, [SG, SL], ["casual", "romantico"], 30, True, "padrao",
     "Ceviches, tiraditos e causas, com peixe do dia."),
    ("Inca Fogo Lento", "peruana", "Pinheiros", 110, [V, SG], ["tranquilo"], 26, True, "jantar",
     "Cozinha andina com batatas nativas, quinoa e pratos de cocção lenta."),
    ("Bistrô Pétala Cinza", "francesa", "Jardins", 190, [V], ["tranquilo", "romantico"], 22, True, "jantar",
     "Clássicos franceses em menu fechado, salão silencioso e serviço à francesa."),
    ("Maison Vinha Clara", "francesa", "Moema", 145, [V, SG], ["romantico"], 24, True, "jantar",
     "Bistrô francês com pratos do dia e uma pequena adega."),
    ("Tasca Azulejo Partido", "portuguesa", "Bela Vista", 118, [SG], ["casual", "tranquilo"], 40, True, "padrao",
     "Bacalhau, polvo e petiscos portugueses numa tasca de azulejos."),
    ("Adega Sete Colinas", "portuguesa", "Moema", 155, [V, SG, SL], ["romantico"], 30, True, "jantar",
     "Cozinha portuguesa de forno e vinhos do Douro e do Alentejo."),
    ("Brasa Pampa Norte", "carnes", "Itaim Bibi", 210, [SG, SL], ["animado"], 80, True, "continuo",
     "Cortes nobres na grelha e buffet de saladas, salão grande e cheio."),
    ("Parrilla Coração de Ferro", "carnes", "Pinheiros", 125, [SG, SL], ["casual", "animado"], 50, True, "continuo",
     "Parrilla de inspiração uruguaia com cortes para compartilhar."),
    ("Ostra & Farol", "frutos_do_mar", "Jardins", 175, [SG, SL], ["tranquilo", "romantico"], 30, True, "jantar",
     "Ostras frescas, peixes inteiros e frutos do mar grelhados."),
    ("Peixaria Cais Doze", "frutos_do_mar", "Vila Madalena", 105, [V, SG, SL], ["casual", "ao_ar_livre"], 40, True, "padrao",
     "Peixe na brasa e moquecas num deque ao ar livre."),
    ("Burger Garagem 77", "hamburgueria", "Pinheiros", 48, [V, SL], ["casual", "animado"], 45, False, "noite",
     "Hambúrguer smash numa antiga oficina, com versão vegetariana de grão-de-bico."),
    ("Chapa Quente da Rua Nove", "hamburgueria", "Mooca", 39, [V], ["casual"], 40, False, "noite",
     "Lanches de chapa grandes e baratos, sem frescura."),
    ("Hambúrguer Satélite", "hamburgueria", "Moema", 62, [V, VG, SG], ["casual", "ao_ar_livre"], 55, True, "noite",
     "Hambúrgueres artesanais com pão sem glúten e opção 100% vegetal."),
    ("Café Ninho de Papel", "cafe_bistro", "Vila Madalena", 42, [V, VG, SG, SL], ["tranquilo"], 20, False, "cafe_noite",
     "Café e bistrô de bairro com pratos leves e cardápio todo adaptável."),
    ("Bistrô Varanda Amarela", "cafe_bistro", "Perdizes", 68, [V, SG], ["tranquilo", "ao_ar_livre"], 30, True, "padrao",
     "Pratos do dia de bistrô numa varanda com plantas."),
    ("Casa de Chá Neblina", "cafe_bistro", "Brooklin", 38, [V, VG, SL], ["tranquilo"], 18, False, "cafe",
     "Chás, tortas e sanduíches leves; fecha no começo da noite."),
]

HOUR_PROFILES = {
    # Almoço + jantar de terça a domingo; domingo só almoço. Segunda fechado.
    "padrao": {"seg": [], "ter": ["12:00-15:00", "19:00-23:00"], "qua": ["12:00-15:00", "19:00-23:00"],
               "qui": ["12:00-15:00", "19:00-23:00"], "sex": ["12:00-15:00", "19:00-23:30"],
               "sab": ["12:00-16:00", "19:00-23:30"], "dom": ["12:00-17:00"]},
    # Só jantar, de terça a sábado.
    "jantar": {"seg": [], "ter": ["19:30-23:00"], "qua": ["19:30-23:00"], "qui": ["19:30-23:00"],
               "sex": ["19:30-23:59"], "sab": ["19:30-23:59"], "dom": []},
    # Noite todos os dias (pizzarias, hamburguerias).
    "noite": {d: ["18:00-23:30"] for d in REF["weekdays"]},
    # Bar: fim de tarde até tarde, fechado na segunda.
    "bar": {"seg": [], "ter": ["17:00-23:59"], "qua": ["17:00-23:59"], "qui": ["17:00-23:59"],
            "sex": ["17:00-23:59"], "sab": ["13:00-23:59"], "dom": ["13:00-22:00"]},
    # Corrido do almoço ao jantar (churrascarias).
    "continuo": {d: ["12:00-23:00"] for d in REF["weekdays"]},
    # Café diurno.
    "cafe": {"seg": ["08:00-19:00"], "ter": ["08:00-19:00"], "qua": ["08:00-19:00"], "qui": ["08:00-19:00"],
             "sex": ["08:00-19:00"], "sab": ["09:00-19:00"], "dom": ["09:00-18:00"]},
    # Café que vira bistrô à noite.
    "cafe_noite": {"seg": [], "ter": ["09:00-22:00"], "qua": ["09:00-22:00"], "qui": ["09:00-22:00"],
                   "sex": ["09:00-22:30"], "sab": ["09:00-22:30"], "dom": ["09:00-18:00"]},
}

BENEFITS = [
    "10% de desconto na conta para grupos de 4 ou mais (simulado)",
    "Sobremesa cortesia para o aniversariante (simulado)",
    "Drink sem álcool de boas-vindas (simulado)",
    "Entrada para dividir por conta da casa (simulado)",
    None, None, None,
]


def slugify(name: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return "-".join("".join(c if c.isalnum() else " " for c in s).split())


def jitter(lat: float, lng: float, rng: random.Random, max_m: float = 650) -> tuple[float, float]:
    """Desloca o ponto em até max_m metros, numa direção aleatória."""
    dist = rng.uniform(80, max_m)
    ang = rng.uniform(0, 2 * math.pi)
    dlat = (dist * math.cos(ang)) / 111_320
    dlng = (dist * math.sin(ang)) / (111_320 * math.cos(math.radians(lat)))
    return round(lat + dlat, 6), round(lng + dlng, 6)


def build() -> list[dict]:
    rng = random.Random(20261121)
    out = []
    for i, (name, cuisine, hood, price, diet, amb, cap, res, hours, desc) in enumerate(RESTAURANTS, start=1):
        c = REF["neighborhoods"][hood]
        lat, lng = jitter(c["lat"], c["lng"], rng)
        slug = slugify(name)
        out.append({
            "id": str(uuid.uuid5(NAMESPACE, slug)),
            "slug": slug,
            "name": name,
            "cuisine": cuisine,
            "description": desc,
            "neighborhood": hood,
            "city": "São Paulo",
            "latitude": lat,
            "longitude": lng,
            "avg_price": price,
            "dietary_options": sorted(diet),
            "capacity": cap,
            "ambiences": amb,
            "opening_hours": HOUR_PROFILES[hours],
            # Probabilidade (0-1) de haver mesa num horário em que o restaurante está aberto.
            # A disponibilidade de cada data/hora é derivada dela de forma determinística no backend.
            "availability_rate": round(rng.uniform(0.82, 0.98), 2),
            "rating": round(rng.uniform(3.9, 4.9), 1),
            "rating_count": rng.randint(40, 900),
            "simulated_benefit": rng.choice(BENEFITS),
            "accepts_reservation": res,
            "is_fictional": True,
        })
    return out


if __name__ == "__main__":
    data = build()
    (HERE / "restaurants_seed.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{len(data)} restaurantes gravados em data/restaurants_seed.json")
