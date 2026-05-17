import os
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from tkinter import ttk


class DashboardWindow(ctk.CTkToplevel):
    def __init__(self, parent, db_path="gravacoes.db", videos_folder="videos_gravados"):
        super().__init__(parent)
        self.title("Dashboard Analítico")
        self.minsize(1100, 720)
        self.db_path = db_path
        self.videos_folder = Path(videos_folder)

        self.after(80, self._configurar_abertura)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_body()
        self.carregar_dashboard()

    def _configurar_abertura(self):
        self.state("zoomed")
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.after(300, lambda: self.attributes("-topmost", False))

    def _build_header(self):
        header = ctk.CTkFrame(self, corner_radius=16)
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=0)

        ctk.CTkLabel(
            header,
            text="Dashboard Analítico do Empacotamento",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(14, 4))

        ctk.CTkLabel(
            header,
            text="Indicadores, gráficos operacionais, classificação de tempo e consistência entre banco e pasta.",
            font=ctk.CTkFont(size=13),
            text_color="#5f6368",
        ).grid(row=1, column=0, sticky="w", padx=18, pady=(0, 14))

        ctk.CTkButton(
            header,
            text="Atualizar Dashboard",
            command=self.carregar_dashboard,
            height=38,
            corner_radius=12,
        ).grid(row=0, column=1, rowspan=2, padx=18, pady=14, sticky="e")

    def _build_body(self):
        body = ctk.CTkFrame(self, corner_radius=16, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        self.cards_frame = ctk.CTkFrame(body, corner_radius=16)
        self.cards_frame.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        for col in range(5):
            self.cards_frame.grid_columnconfigure(col, weight=1, uniform="cards")

        self.card_total = self._create_card(self.cards_frame, "Vídeos válidos", "0", 0)
        self.card_tempo_total = self._create_card(self.cards_frame, "Tempo total gravado", "00:00", 1)
        self.card_mediana = self._create_card(self.cards_frame, "Mediana", "00:00", 2)
        self.card_minimo = self._create_card(self.cards_frame, "Menor duração", "00:00", 3)
        self.card_consistencia = self._create_card(self.cards_frame, "Consistência", "0%", 4)

        content = ctk.CTkFrame(body, corner_radius=16)
        content.grid(row=1, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=2)
        content.grid_rowconfigure(0, weight=1)

        self.left_panel = ctk.CTkFrame(content, corner_radius=16)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=0)
        self.left_panel.grid_rowconfigure(0, weight=1)
        self.left_panel.grid_columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self.left_panel)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)

        self.tab_graficos = ctk.CTkFrame(self.notebook, corner_radius=0)
        self.tab_top = ctk.CTkFrame(self.notebook, corner_radius=0)
        self.tab_alertas = ctk.CTkFrame(self.notebook, corner_radius=0)

        self.notebook.add(self.tab_graficos, text="Gráficos")
        self.notebook.add(self.tab_top, text="Top Pedidos")
        self.notebook.add(self.tab_alertas, text="Fora do Padrão")

        self._build_graphs_tab()
        self._build_top_tab()
        self._build_alerts_tab()

        self.right_panel = ctk.CTkFrame(content, corner_radius=16)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=0)
        self.right_panel.grid_columnconfigure(0, weight=1)
        self.right_panel.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            self.right_panel,
            text="Classificação e Integridade",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 10))

        self.classificacao_box = ctk.CTkTextbox(self.right_panel, height=130, corner_radius=12)
        self.classificacao_box.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))

        self.integridade_box = ctk.CTkTextbox(self.right_panel, height=130, corner_radius=12)
        self.integridade_box.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))

        self.resumo_tree = ttk.Treeview(
            self.right_panel,
            columns=("indicador", "valor"),
            show="headings",
            height=10,
        )
        self.resumo_tree.heading("indicador", text="Indicador")
        self.resumo_tree.heading("valor", text="Valor")
        self.resumo_tree.column("indicador", width=220, anchor="w")
        self.resumo_tree.column("valor", width=110, anchor="center")
        self.resumo_tree.grid(row=3, column=0, sticky="nsew", padx=16, pady=(0, 16))

    def _build_graphs_tab(self):
        self.tab_graficos.grid_columnconfigure((0, 1), weight=1)
        self.tab_graficos.grid_rowconfigure((0, 1), weight=1)

        self.fig_videos = Figure(figsize=(5, 3), dpi=100)
        self.ax_videos = self.fig_videos.add_subplot(111)
        self.canvas_videos = FigureCanvasTkAgg(self.fig_videos, master=self.tab_graficos)
        self.canvas_videos.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        self.fig_tempo = Figure(figsize=(5, 3), dpi=100)
        self.ax_tempo = self.fig_tempo.add_subplot(111)
        self.canvas_tempo = FigureCanvasTkAgg(self.fig_tempo, master=self.tab_graficos)
        self.canvas_tempo.get_tk_widget().grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

        self.fig_classificacao = Figure(figsize=(5, 3), dpi=100)
        self.ax_classificacao = self.fig_classificacao.add_subplot(111)
        self.canvas_classificacao = FigureCanvasTkAgg(self.fig_classificacao, master=self.tab_graficos)
        self.canvas_classificacao.get_tk_widget().grid(row=1, column=0, columnspan=2, sticky="nsew", padx=10, pady=10)

    def _build_top_tab(self):
        self.tab_top.grid_columnconfigure(0, weight=1)
        self.tab_top.grid_rowconfigure(0, weight=1)
        self.top_tree = ttk.Treeview(
            self.tab_top,
            columns=("pedido", "qtd", "tempo_total", "tempo_medio"),
            show="headings",
            height=14,
        )
        self.top_tree.heading("pedido", text="Pedido")
        self.top_tree.heading("qtd", text="Qtd. Vídeos")
        self.top_tree.heading("tempo_total", text="Tempo Total")
        self.top_tree.heading("tempo_medio", text="Tempo Médio")
        self.top_tree.column("pedido", width=180, anchor="w")
        self.top_tree.column("qtd", width=100, anchor="center")
        self.top_tree.column("tempo_total", width=140, anchor="center")
        self.top_tree.column("tempo_medio", width=140, anchor="center")
        self.top_tree.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)

    def _build_alerts_tab(self):
        self.tab_alertas.grid_columnconfigure(0, weight=1)
        self.tab_alertas.grid_rowconfigure(0, weight=1)
        self.alert_tree = ttk.Treeview(
            self.tab_alertas,
            columns=("pedido", "inicio", "duracao", "classificacao", "alerta"),
            show="headings",
            height=14,
        )
        self.alert_tree.heading("pedido", text="Pedido")
        self.alert_tree.heading("inicio", text="Início")
        self.alert_tree.heading("duracao", text="Duração")
        self.alert_tree.heading("classificacao", text="Classe")
        self.alert_tree.heading("alerta", text="Alerta")
        self.alert_tree.column("pedido", width=160, anchor="w")
        self.alert_tree.column("inicio", width=150, anchor="center")
        self.alert_tree.column("duracao", width=90, anchor="center")
        self.alert_tree.column("classificacao", width=100, anchor="center")
        self.alert_tree.column("alerta", width=240, anchor="w")
        self.alert_tree.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)

    def _create_card(self, parent, title, value, column):
        frame = ctk.CTkFrame(parent, corner_radius=16, height=92)
        frame.grid(row=0, column=column, sticky="nsew", padx=8, pady=10)
        frame.grid_propagate(False)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame,
            text=title,
            text_color="#687076",
            font=ctk.CTkFont(size=13),
            wraplength=180,
            justify="left",
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))

        value_label = ctk.CTkLabel(
            frame,
            text=value,
            font=ctk.CTkFont(size=26, weight="bold"),
        )
        value_label.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 12))
        return value_label

    def carregar_dashboard(self):
        dados = self._buscar_dados_validos()
        self._atualizar_cards(dados)
        self._atualizar_resumo_lateral(dados)
        self._atualizar_tabela_top(dados)
        self._atualizar_alertas(dados)
        self._plot_videos_por_dia(dados)
        self._plot_tempo_por_dia(dados)
        self._plot_classificacao(dados)

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _buscar_dados_validos(self):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT pedido, data_inicio, data_fim, duracao_segundos, tamanho_bytes,
                       status, existe_arquivo, caminho_arquivo
                FROM videos
                ORDER BY data_inicio ASC
                """
            )
            rows = cur.fetchall()

        dados = []
        for pedido, data_inicio, data_fim, duracao, tamanho, status, existe_arquivo, caminho in rows:
            try:
                dt_inicio = datetime.strptime(data_inicio, "%Y-%m-%d %H:%M:%S") if data_inicio else None
            except ValueError:
                dt_inicio = None

            dados.append(
                {
                    "pedido": pedido,
                    "data_inicio": dt_inicio,
                    "data_inicio_str": data_inicio,
                    "data_fim": data_fim,
                    "duracao": float(duracao or 0),
                    "tamanho": int(tamanho or 0),
                    "status": status,
                    "existe_arquivo": int(existe_arquivo or 0),
                    "caminho": caminho,
                }
            )
        return dados

    def _atualizar_cards(self, dados):
        validos = [d for d in dados if d["existe_arquivo"] == 1]
        duracoes = [d["duracao"] for d in validos]
        total_videos = len(validos)
        tempo_total = sum(duracoes)
        mediana = statistics.median(duracoes) if duracoes else 0
        minimo = min(duracoes) if duracoes else 0
        consistencia = self._calcular_consistencia(dados)

        self.card_total.configure(text=str(total_videos))
        self.card_tempo_total.configure(text=self._formatar_tempo(tempo_total))
        self.card_mediana.configure(text=self._formatar_tempo(mediana))
        self.card_minimo.configure(text=self._formatar_tempo(minimo))
        self.card_consistencia.configure(text=f"{consistencia:.1f}%")

    def _atualizar_resumo_lateral(self, dados):
        validos = [d for d in dados if d["existe_arquivo"] == 1]
        duracoes = [d["duracao"] for d in validos]
        classificacao = self._classificar_duracoes(validos)
        consistencia = self._calcular_consistencia(dados)

        self.classificacao_box.configure(state="normal")
        self.classificacao_box.delete("1.0", "end")
        self.classificacao_box.insert(
            "1.0",
            "Classificação dos vídeos por duração\n\n"
            f"• Rápida: {classificacao['rapida']}\n"
            f"• Normal: {classificacao['normal']}\n"
            f"• Lenta: {classificacao['lenta']}\n\n"
            "Regra atual:\n"
            "• Rápida: < 60 s\n"
            "• Normal: 60 s até 180 s\n"
            "• Lenta: > 180 s\n",
        )
        self.classificacao_box.configure(state="disabled")

        arquivos_pasta = list(self.videos_folder.glob("*.avi")) if self.videos_folder.exists() else []
        ativos_banco = len([d for d in dados if d["existe_arquivo"] == 1])
        excluidos = len([d for d in dados if d["status"] == "excluido" or d["existe_arquivo"] == 0])
        media = statistics.mean(duracoes) if duracoes else 0
        desvio = statistics.pstdev(duracoes) if len(duracoes) > 1 else 0

        self.integridade_box.configure(state="normal")
        self.integridade_box.delete("1.0", "end")
        self.integridade_box.insert(
            "1.0",
            "Integridade entre banco e pasta\n\n"
            f"• Arquivos na pasta: {len(arquivos_pasta)}\n"
            f"• Registros ativos no banco: {ativos_banco}\n"
            f"• Registros excluídos: {excluidos}\n"
            f"• Consistência: {consistencia:.1f}%\n\n"
            f"• Média das durações: {self._formatar_tempo(media)}\n"
            f"• Desvio padrão: {self._formatar_tempo(desvio)}\n",
        )
        self.integridade_box.configure(state="disabled")

        for item in self.resumo_tree.get_children():
            self.resumo_tree.delete(item)

        resumo_linhas = [
            ("Tempo máximo", self._formatar_tempo(max(duracoes) if duracoes else 0)),
            ("Tempo médio", self._formatar_tempo(statistics.mean(duracoes) if duracoes else 0)),
            ("Tempo mínimo", self._formatar_tempo(min(duracoes) if duracoes else 0)),
            ("Mediana", self._formatar_tempo(statistics.median(duracoes) if duracoes else 0)),
            ("Qtd. pedidos únicos", str(len({d['pedido'] for d in validos}))),
            ("Qtd. vídeos fora do padrão", str(len(self._detectar_outliers(validos)))),
        ]
        for indicador, valor in resumo_linhas:
            self.resumo_tree.insert("", "end", values=(indicador, valor))

    def _atualizar_tabela_top(self, dados):
        for item in self.top_tree.get_children():
            self.top_tree.delete(item)

        agrupado = defaultdict(list)
        for d in dados:
            if d["existe_arquivo"] == 1:
                agrupado[d["pedido"]].append(d["duracao"])

        ranking = []
        for pedido, duracoes in agrupado.items():
            ranking.append((pedido, len(duracoes), sum(duracoes), statistics.mean(duracoes)))

        ranking.sort(key=lambda x: x[2], reverse=True)

        for pedido, qtd, total, media in ranking[:10]:
            self.top_tree.insert(
                "",
                "end",
                values=(pedido, qtd, self._formatar_tempo(total), self._formatar_tempo(media)),
            )

    def _atualizar_alertas(self, dados):
        for item in self.alert_tree.get_children():
            self.alert_tree.delete(item)

        outliers = self._detectar_outliers([d for d in dados if d["existe_arquivo"] == 1])
        for d in outliers:
            classe = self._classificar_tempo(d["duracao"])
            alerta = "Acima do comportamento esperado" if d["duracao"] > d["limite_superior"] else "Abaixo do comportamento esperado"
            self.alert_tree.insert(
                "",
                "end",
                values=(
                    d["pedido"],
                    d["data_inicio_str"],
                    self._formatar_tempo(d["duracao"]),
                    classe,
                    alerta,
                ),
            )

    def _plot_videos_por_dia(self, dados):
        self.ax_videos.clear()
        contagem = Counter()
        for d in dados:
            if d["existe_arquivo"] == 1 and d["data_inicio"]:
                contagem[d["data_inicio"].strftime("%d/%m")] += 1

        labels = list(contagem.keys())
        values = list(contagem.values())

        if values:
            self.ax_videos.bar(labels, values)
            self.ax_videos.set_title("Vídeos por dia")
            self.ax_videos.set_ylabel("Quantidade")
            self.ax_videos.tick_params(axis="x", rotation=45)
        else:
            self.ax_videos.text(0.5, 0.5, "Sem dados para exibir", ha="center", va="center")
            self.ax_videos.set_title("Vídeos por dia")
        self.fig_videos.tight_layout()
        self.canvas_videos.draw()

    def _plot_tempo_por_dia(self, dados):
        self.ax_tempo.clear()
        tempos = defaultdict(float)
        for d in dados:
            if d["existe_arquivo"] == 1 and d["data_inicio"]:
                tempos[d["data_inicio"].strftime("%d/%m")] += d["duracao"]

        labels = list(tempos.keys())
        values = [v / 60 for v in tempos.values()]

        if values:
            self.ax_tempo.plot(labels, values, marker="o")
            self.ax_tempo.set_title("Tempo total gravado por dia")
            self.ax_tempo.set_ylabel("Minutos")
            self.ax_tempo.tick_params(axis="x", rotation=45)
        else:
            self.ax_tempo.text(0.5, 0.5, "Sem dados para exibir", ha="center", va="center")
            self.ax_tempo.set_title("Tempo total gravado por dia")
        self.fig_tempo.tight_layout()
        self.canvas_tempo.draw()

    def _plot_classificacao(self, dados):
        self.ax_classificacao.clear()
        classificacao = self._classificar_duracoes([d for d in dados if d["existe_arquivo"] == 1])
        labels = ["Rápida", "Normal", "Lenta"]
        values = [classificacao["rapida"], classificacao["normal"], classificacao["lenta"]]

        if sum(values) > 0:
            self.ax_classificacao.bar(labels, values)
            self.ax_classificacao.set_title("Classificação das gravações")
            self.ax_classificacao.set_ylabel("Quantidade")
        else:
            self.ax_classificacao.text(0.5, 0.5, "Sem dados para exibir", ha="center", va="center")
            self.ax_classificacao.set_title("Classificação das gravações")
        self.fig_classificacao.tight_layout()
        self.canvas_classificacao.draw()

    def _classificar_duracoes(self, dados):
        resultado = {"rapida": 0, "normal": 0, "lenta": 0}
        for d in dados:
            classe = self._classificar_tempo(d["duracao"])
            resultado[classe] += 1
        return resultado

    def _classificar_tempo(self, segundos):
        if segundos < 60:
            return "rapida"
        if segundos <= 180:
            return "normal"
        return "lenta"

    def _detectar_outliers(self, dados):
        if len(dados) < 2:
            return []

        duracoes = [d["duracao"] for d in dados]
        media = statistics.mean(duracoes)
        desvio = statistics.pstdev(duracoes)
        if desvio == 0:
            return []

        limite_superior = media + (2 * desvio)
        limite_inferior = max(0, media - (2 * desvio))

        outliers = []
        for d in dados:
            if d["duracao"] > limite_superior or d["duracao"] < limite_inferior:
                item = dict(d)
                item["limite_superior"] = limite_superior
                item["limite_inferior"] = limite_inferior
                outliers.append(item)
        return outliers

    def _calcular_consistencia(self, dados):
        if not dados:
            return 100.0

        consistentes = 0
        for d in dados:
            existe_no_disco = os.path.exists(d["caminho"]) if d["caminho"] else False
            if int(existe_no_disco) == int(d["existe_arquivo"]):
                consistentes += 1
        return (consistentes / len(dados)) * 100

    @staticmethod
    def _formatar_tempo(segundos):
        try:
            segundos = int(round(float(segundos)))
        except (TypeError, ValueError):
            segundos = 0
        horas = segundos // 3600
        minutos = (segundos % 3600) // 60
        resto = segundos % 60
        if horas > 0:
            return f"{horas:02d}:{minutos:02d}:{resto:02d}"
        return f"{minutos:02d}:{resto:02d}"
