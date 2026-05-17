import serial
import serial.tools.list_ports
import cv2
import os
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
import customtkinter as ctk
from tkinter import messagebox, ttk
from PIL import Image
from dashboard_window import DashboardWindow

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

class DatabaseManager:
    def __init__(self, db_path="gravacoes.db"):
        self.db_path = db_path
        self._criar_tabelas()


    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _criar_tabelas(self):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pedido TEXT NOT NULL,
                    nome_arquivo TEXT NOT NULL,
                    caminho_arquivo TEXT NOT NULL,
                    data_inicio TEXT NOT NULL,
                    data_fim TEXT,
                    duracao_segundos REAL DEFAULT 0,
                    tamanho_bytes INTEGER DEFAULT 0,
                    largura INTEGER DEFAULT 0,
                    altura INTEGER DEFAULT 0,
                    fps REAL DEFAULT 0,
                    origem_camera TEXT,
                    status TEXT DEFAULT 'gravado',
                    observacoes TEXT,
                    existe_arquivo INTEGER DEFAULT 1,
                    excluido_em TEXT
                )
                """
            )

            # Ajusta bancos antigos que ainda não têm as colunas novas.
            colunas = {row[1] for row in cur.execute("PRAGMA table_info(videos)").fetchall()}
            if "existe_arquivo" not in colunas:
                cur.execute("ALTER TABLE videos ADD COLUMN existe_arquivo INTEGER DEFAULT 1")
            if "excluido_em" not in colunas:
                cur.execute("ALTER TABLE videos ADD COLUMN excluido_em TEXT")
            conn.commit()

    def inserir_video(self, dados: dict):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO videos (
                    pedido, nome_arquivo, caminho_arquivo, data_inicio, data_fim,
                    duracao_segundos, tamanho_bytes, largura, altura, fps,
                    origem_camera, status, observacoes, existe_arquivo, excluido_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dados["pedido"],
                    dados["nome_arquivo"],
                    dados["caminho_arquivo"],
                    dados["data_inicio"],
                    dados["data_fim"],
                    dados["duracao_segundos"],
                    dados["tamanho_bytes"],
                    dados["largura"],
                    dados["altura"],
                    dados["fps"],
                    dados["origem_camera"],
                    dados.get("status", "gravado"),
                    dados.get("observacoes", ""),
                    dados.get("existe_arquivo", 1),
                    dados.get("excluido_em"),
                ),
            )
            conn.commit()

    def listar_videos(self, limite=300):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, pedido, nome_arquivo, data_inicio, duracao_segundos,
                       tamanho_bytes, largura, altura, status, existe_arquivo, caminho_arquivo
                FROM videos
                ORDER BY id DESC
                LIMIT ?
                """,
                (limite,),
            )
            return cur.fetchall()

    def obter_video_por_id(self, video_id):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, pedido, nome_arquivo, caminho_arquivo, status, existe_arquivo
                FROM videos
                WHERE id = ?
                """,
                (video_id,),
            )
            return cur.fetchone()

    def marcar_como_excluido(self, video_id):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE videos
                SET status = 'excluido', existe_arquivo = 0, excluido_em = ?
                WHERE id = ?
                """,
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), video_id),
            )
            conn.commit()

    def atualizar_presenca_arquivo(self, video_id, existe_arquivo, status=None):
        with self._connect() as conn:
            cur = conn.cursor()
            if status is None:
                cur.execute(
                    "UPDATE videos SET existe_arquivo = ? WHERE id = ?",
                    (existe_arquivo, video_id),
                )
            else:
                cur.execute(
                    "UPDATE videos SET existe_arquivo = ?, status = ?, excluido_em = ? WHERE id = ?",
                    (existe_arquivo, status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), video_id),
                )
            conn.commit()

    def obter_metricas(self):
        with self._connect() as conn:
            cur = conn.cursor()

            cur.execute("SELECT COUNT(*) FROM videos")
            total_registros = cur.fetchone()[0] or 0

            cur.execute("SELECT COUNT(*) FROM videos WHERE existe_arquivo = 1")
            total_videos_ativos = cur.fetchone()[0] or 0

            cur.execute("SELECT COUNT(DISTINCT pedido) FROM videos WHERE existe_arquivo = 1")
            total_pedidos = cur.fetchone()[0] or 0

            cur.execute("SELECT COALESCE(MAX(duracao_segundos), 0) FROM videos WHERE existe_arquivo = 1")
            max_duracao = cur.fetchone()[0] or 0

            cur.execute("SELECT COALESCE(AVG(duracao_segundos), 0) FROM videos WHERE existe_arquivo = 1")
            media_duracao = cur.fetchone()[0] or 0

            cur.execute("SELECT COALESCE(SUM(tamanho_bytes), 0) FROM videos WHERE existe_arquivo = 1")
            total_armazenado = cur.fetchone()[0] or 0

            cur.execute("SELECT COUNT(*) FROM videos WHERE status = 'excluido'")
            total_excluidos = cur.fetchone()[0] or 0

            return {
                "total_registros": total_registros,
                "total_videos": total_videos_ativos,
                "total_pedidos": total_pedidos,
                "max_duracao": max_duracao,
                "media_duracao": media_duracao,
                "total_armazenado": total_armazenado,
                "total_excluidos": total_excluidos,
            }


class CameraStream:
    def __init__(self):
        self.cap = None
        self.running = False
        self.thread = None
        self.frame = None
        self.lock = threading.Lock()
        self.url = None

    def iniciar(self, url):
        self.parar()
        self.url = url
        self.cap = cv2.VideoCapture(url)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not self.cap.isOpened():
            self.cap = None
            return False

        self.running = True
        self.thread = threading.Thread(target=self._loop_captura, daemon=True)
        self.thread.start()
        return True

    def _loop_captura(self):
        while self.running and self.cap is not None:
            ret, frame = self.cap.read()
            if ret:
                with self.lock:
                    self.frame = frame
            else:
                time.sleep(0.02)

    def get_frame(self):
        with self.lock:
            if self.frame is None:
                return None
            return self.frame.copy()

    def parar(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1)
        self.thread = None
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.frame = None


class AppCameraIP:
    def __init__(self, root):
        self.root = root
        self.root.title("Sistema de Gravação Inteligente")
        self.root.minsize(1180, 760)
        self.root.after(100, lambda: self.root.state("zoomed"))

        self.db = DatabaseManager()
        self.camera = CameraStream()

        self.gravando = False
        self.writer = None
        self.frame_atual = None
        self.inicio_gravacao = None
        self.nome_arquivo_atual = None
        self.caminho_arquivo_atual = None
        self.serial_conn = None
        self.serial_thread = None
        self.serial_running = False
        self.porta_com_var = ctk.StringVar(value="COM3")
        self.fps_gravacao = 15.0
        self.resolucao_gravacao = (640, 480)

        self.pasta_videos = Path("videos_gravados")
        self.pasta_videos.mkdir(exist_ok=True)

        self._montar_interface()
        self.sincronizar_com_pasta(mostrar_mensagem=False)
        self.atualizar_dashboard()
        self.atualizar_tabela()
        self.atualizar_preview()
        self.atualizar_cronometro()

        self.root.protocol("WM_DELETE_WINDOW", self.fechar_app)

    def _montar_interface(self):
        self.root.grid_columnconfigure(0, weight=0)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self.root, width=330, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(18, weight=1)
        self.sidebar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.sidebar,
            text="Empacotamento\nMonitorado",
            font=ctk.CTkFont(size=26, weight="bold"),
            justify="left",
        ).grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        ctk.CTkLabel(
            self.sidebar,
            text="Controle de gravações, métricas e rastreabilidade dos vídeos.",
            justify="left",
            wraplength=280,
            text_color="#5b5b5b",
            font=ctk.CTkFont(size=14),
        ).grid(row=1, column=0, padx=20, pady=(0, 16), sticky="ew")

        self.entry_com = ctk.CTkEntry(self.sidebar, textvariable=self.porta_com_var, placeholder_text="Porta COM do WeMos")
        self.entry_com.grid(row=5, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.entry_url = ctk.CTkEntry(self.sidebar, placeholder_text="URL da câmera IP")
        self.entry_url.insert(0, "http://192.168.0.100:8080/video")
        self.entry_url.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.entry_pedido = ctk.CTkEntry(self.sidebar, placeholder_text="Número do pedido")
        self.entry_pedido.grid(row=3, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.entry_observacao = ctk.CTkEntry(self.sidebar, placeholder_text="Observação opcional")
        self.entry_observacao.grid(row=4, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.btn_conectar = ctk.CTkButton(self.sidebar, text="Conectar câmera", command=self.conectar_camera, height=40, corner_radius=12)
        self.btn_conectar.grid(row=6, column=0, padx=20, pady=(0, 10), sticky="ew")
        
        self.btn_serial = ctk.CTkButton(
            self.sidebar,
            text="Conectar Arduino",
            command=self.conectar_serial,
            height=40,
            corner_radius=12,
            fg_color="#117A65",
            hover_color="#0B5345",
        )
        self.btn_serial.grid(row=7, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.btn_iniciar = ctk.CTkButton(
            self.sidebar,
            text="Iniciar gravação",
            command=self.iniciar_gravacao,
            height=40,
            corner_radius=12,
            state="disabled",
            fg_color="#1f6aa5",
            hover_color="#18527f",
        )
        self.btn_iniciar.grid(row=8, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.btn_parar = ctk.CTkButton(
            self.sidebar,
            text="Parar gravação",
            command=self.parar_gravacao,
            height=40,
            corner_radius=12,
            state="disabled",
            fg_color="#C0392B",
            hover_color="#922B21",
        )
        self.btn_parar.grid(row=9, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.btn_sincronizar = ctk.CTkButton(
            self.sidebar,
            text="Sincronizar pasta e banco",
            command=self.sincronizar_com_pasta,
            height=40,
            corner_radius=12,
            fg_color="#566573",
            hover_color="#34495E",
        )
        self.btn_sincronizar.grid(row=10, column=0, padx=20, pady=(0, 14), sticky="ew")

        self.btn_dashboard = ctk.CTkButton(
            self.sidebar,
            text="Abrir dashboard",
            command=self.abrir_dashboard,
            height=40,
            corner_radius=12,
            fg_color="#2E86C1",
            hover_color="#1F618D",
        )
        self.btn_dashboard.grid(row=11, column=0, padx=20, pady=(0, 14), sticky="ew")


        self.status_var = ctk.StringVar(value="Status: Desconectado")
        self.label_status = ctk.CTkLabel(
            self.sidebar,
            textvariable=self.status_var,
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#B03A2E",
            wraplength=280,
            justify="left",
        )
        self.label_status.grid(row=12, column=0, padx=20, pady=(0, 8), sticky="ew")

        self.cronometro_var = ctk.StringVar(value="Tempo de gravação: 00:00")
        ctk.CTkLabel(
            self.sidebar,
            textvariable=self.cronometro_var,
            font=ctk.CTkFont(size=18, weight="bold"),
            wraplength=280,
            justify="left",
        ).grid(row=13, column=0, padx=20, pady=(0, 8), sticky="ew")

        self.arquivo_var = ctk.StringVar(value="Arquivo atual: nenhum")
        ctk.CTkLabel(
            self.sidebar,
            textvariable=self.arquivo_var,
            justify="left",
            wraplength=280,
            text_color="#666666",
        ).grid(row=14, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.selecao_var = ctk.StringVar(value="ID selecionado: nenhum")
        ctk.CTkLabel(
            self.sidebar,
            textvariable=self.selecao_var,
            justify="left",
            wraplength=280,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=15, column=0, padx=20, pady=(0, 8), sticky="ew")

        self.btn_excluir = ctk.CTkButton(
            self.sidebar,
            text="Excluir vídeo selecionado",
            command=self.excluir_video_selecionado,
            height=40,
            corner_radius=12,
            fg_color="#7D3C98",
            hover_color="#5B2C6F",
        )
        self.btn_excluir.grid(row=16, column=0, padx=20, pady=(0, 14), sticky="ew")

        ctk.CTkLabel(
            self.sidebar,
            text="Indicadores disponíveis",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=17, column=0, padx=20, pady=(6, 8), sticky="w")

        self.info_box = ctk.CTkTextbox(self.sidebar, height=170, corner_radius=12)
        self.info_box.grid(row=18, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.info_box.insert(
            "1.0",
            "• Total de vídeos gravados\n"
            "• Total de pedidos processados\n"
            "• Tempo máximo de gravação\n"
            "• Tempo médio por gravação\n"
            "• Espaço total armazenado\n"
            "• Total de vídeos excluídos\n"
            "• Consistência entre banco e pasta física\n",
        )
        self.info_box.configure(state="disabled")

        self.main = ctk.CTkFrame(self.root, corner_radius=0, fg_color="#f6f7fb")
        self.main.grid(row=0, column=1, sticky="nsew")
        for col in range(4):
            self.main.grid_columnconfigure(col, weight=1, uniform="cards")
        self.main.grid_rowconfigure(1, weight=3)
        self.main.grid_rowconfigure(2, weight=1)

        self.card_total_videos = self._criar_card(self.main, "Vídeos na pasta", "0", 0)
        self.card_total_pedidos = self._criar_card(self.main, "Pedidos únicos", "0", 1)
        self.card_max = self._criar_card(self.main, "Maior duração", "00:00", 2)
        self.card_media = self._criar_card(self.main, "Tempo médio", "00:00", 3)

        self.preview_frame = ctk.CTkFrame(self.main, corner_radius=18)
        self.preview_frame.grid(row=1, column=0, columnspan=3, padx=(18, 9), pady=(10, 10), sticky="nsew")
        self.preview_frame.grid_rowconfigure(1, weight=1)
        self.preview_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.preview_frame,
            text="Visualização da câmera",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=0, padx=16, pady=(14, 8), sticky="w")

        self.label_video = ctk.CTkLabel(self.preview_frame, text="Câmera não conectada")
        self.label_video.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="nsew")

        self.history_frame = ctk.CTkFrame(self.main, corner_radius=18)
        self.history_frame.grid(row=1, column=3, padx=(9, 18), pady=(10, 10), sticky="nsew")
        self.history_frame.grid_rowconfigure(1, weight=1)
        self.history_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.history_frame,
            text="Últimas gravações",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=0, padx=16, pady=(14, 8), sticky="w")

        tree_container = ctk.CTkFrame(self.history_frame, fg_color="transparent")
        tree_container.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="nsew")
        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tree_container,
            columns=("id", "pedido", "inicio", "duracao", "tamanho", "resolucao", "status"),
            show="headings",
            height=14,
        )
        self.tree.heading("id", text="ID")
        self.tree.heading("pedido", text="Pedido")
        self.tree.heading("inicio", text="Início")
        self.tree.heading("duracao", text="Duração")
        self.tree.heading("tamanho", text="Tamanho")
        self.tree.heading("resolucao", text="Resolução")
        self.tree.heading("status", text="Status")

        self.tree.column("id", width=50, anchor="center", stretch=False)
        self.tree.column("pedido", width=115, anchor="w")
        self.tree.column("inicio", width=135, anchor="w")
        self.tree.column("duracao", width=80, anchor="center", stretch=False)
        self.tree.column("tamanho", width=85, anchor="center", stretch=False)
        self.tree.column("resolucao", width=90, anchor="center", stretch=False)
        self.tree.column("status", width=90, anchor="center", stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        self.bottom_frame = ctk.CTkFrame(self.main, corner_radius=18)
        self.bottom_frame.grid(row=2, column=0, columnspan=4, padx=18, pady=(0, 18), sticky="nsew")
        for col in range(4):
            self.bottom_frame.grid_columnconfigure(col, weight=1, uniform="bottom")

        self.total_armazenado_var = ctk.StringVar(value="Armazenamento total: 0 B")
        self.ultimo_video_var = ctk.StringVar(value="Último vídeo: nenhum")
        self.fonte_var = ctk.StringVar(value="Fonte de vídeo: não conectada")
        self.excluidos_var = ctk.StringVar(value="Vídeos excluídos: 0")

        self._criar_info_inferior(self.bottom_frame, "Armazenamento", self.total_armazenado_var, 0)
        self._criar_info_inferior(self.bottom_frame, "Último arquivo", self.ultimo_video_var, 1)
        self._criar_info_inferior(self.bottom_frame, "Origem da câmera", self.fonte_var, 2)
        self._criar_info_inferior(self.bottom_frame, "Exclusões", self.excluidos_var, 3)

    def abrir_dashboard(self):
        if hasattr(self, "dashboard_window") and self.dashboard_window.winfo_exists():
            self.dashboard_window.lift()
            self.dashboard_window.focus_force()
            self.dashboard_window.attributes("-topmost", True)
            self.root.after(300, lambda: self.dashboard_window.attributes("-topmost", False))
            return

        self.dashboard_window = DashboardWindow(
            self.root,
            db_path="gravacoes.db",
            videos_folder="videos_gravados"
        ) 

    def conectar_serial(self):
        porta = self.porta_com_var.get().strip()

        if not porta:
            messagebox.showwarning("Aviso", "Informe a porta COM do WeMos.")
            return

        try:
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.close()

            self.serial_conn = serial.Serial(porta, 115200, timeout=1)
            time.sleep(2)

            self.serial_running = True
            self.serial_thread = threading.Thread(target=self.escutar_serial, daemon=True)
            self.serial_thread.start()

            messagebox.showinfo("Sucesso", f"Comunicação serial conectada na porta {porta}.")
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível conectar na porta {porta}.\n\nDetalhe: {e}")

    def escutar_serial(self):
        while self.serial_running and self.serial_conn and self.serial_conn.is_open:
            try:
                if self.serial_conn.in_waiting:
                    comando = self.serial_conn.readline().decode(errors="ignore").strip()

                    if comando:
                        print("Comando serial recebido:", comando)

                    if comando == "START":
                        self.root.after(0, self.iniciar_gravacao)

                    elif comando == "STOP":
                        self.root.after(0, self.parar_gravacao)

            except Exception as e:
                print("Erro na leitura serial:", e)
                break

    def _criar_card(self, parent, titulo, valor, coluna):
        frame = ctk.CTkFrame(parent, corner_radius=18, height=98)
        padx = (18, 9) if coluna == 0 else (9, 18) if coluna == 3 else 9
        frame.grid(row=0, column=coluna, padx=padx, pady=(18, 10), sticky="nsew")
        frame.grid_propagate(False)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame,
            text=titulo,
            font=ctk.CTkFont(size=14),
            text_color="#666666",
            wraplength=220,
            justify="left",
        ).grid(row=0, column=0, padx=16, pady=(14, 4), sticky="ew")

        valor_label = ctk.CTkLabel(
            frame,
            text=valor,
            font=ctk.CTkFont(size=28, weight="bold"),
            anchor="w",
            justify="left",
        )
        valor_label.grid(row=1, column=0, padx=16, pady=(0, 14), sticky="ew")
        return valor_label

    def _criar_info_inferior(self, parent, titulo, variavel, coluna):
        frame = ctk.CTkFrame(parent, corner_radius=14)
        frame.grid(row=0, column=coluna, padx=10, pady=16, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text=titulo, font=ctk.CTkFont(size=14), text_color="#666666").grid(row=0, column=0, padx=14, pady=(14, 4), sticky="w")
        ctk.CTkLabel(
            frame,
            textvariable=variavel,
            font=ctk.CTkFont(size=16, weight="bold"),
            wraplength=240,
            justify="left",
        ).grid(row=1, column=0, padx=14, pady=(0, 14), sticky="ew")

    def conectar_camera(self):
        url = self.entry_url.get().strip()
        if not url:
            messagebox.showwarning("Aviso", "Informe a URL da câmera IP.")
            return

        sucesso = self.camera.iniciar(url)
        if not sucesso:
            self.status_var.set("Status: Falha ao conectar")
            self.label_status.configure(text_color="#B03A2E")
            self.btn_iniciar.configure(state="disabled")
            messagebox.showerror("Erro", "Não foi possível abrir a câmera IP.")
            return

        self.status_var.set("Status: Câmera conectada")
        self.label_status.configure(text_color="#1E8449")
        self.btn_iniciar.configure(state="normal")
        self.fonte_var.set(f"Fonte de vídeo: {url}")
        messagebox.showinfo("Sucesso", "Câmera conectada com sucesso.")

    def iniciar_gravacao(self):
        if self.gravando:
            messagebox.showinfo("Informação", "A gravação já está em andamento.")
            return

        frame = self.camera.get_frame()
        if frame is None:
            messagebox.showwarning("Aviso", "Conecte a câmera e aguarde o preview aparecer antes de gravar.")
            return

        pedido = self.entry_pedido.get().strip()
        if not pedido:
            messagebox.showwarning("Aviso", "Informe o número do pedido.")
            return

        self.inicio_gravacao = datetime.now()
        timestamp = self.inicio_gravacao.strftime("%Y-%m-%d_%H-%M-%S")
        nome_arquivo = f"pedido_{pedido}_{timestamp}.avi"
        caminho_arquivo = self.pasta_videos / nome_arquivo

        altura, largura = frame.shape[:2]
        self.resolucao_gravacao = (largura, altura)
        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        self.writer = cv2.VideoWriter(str(caminho_arquivo), fourcc, self.fps_gravacao, (largura, altura))

        if not self.writer.isOpened():
            self.writer = None
            messagebox.showerror("Erro", "Não foi possível criar o arquivo de vídeo.")
            return

        self.gravando = True
        self.nome_arquivo_atual = nome_arquivo
        self.caminho_arquivo_atual = str(caminho_arquivo)
        self.status_var.set("Status: Gravando")
        self.label_status.configure(text_color="#C0392B")
        self.arquivo_var.set(f"Arquivo atual: {self.caminho_arquivo_atual}")
        self.btn_iniciar.configure(state="disabled")
        self.btn_parar.configure(state="normal")
        self.ultimo_video_var.set(f"Último vídeo: {nome_arquivo}")

    def parar_gravacao(self):
        if not self.gravando:
            return

        self.gravando = False
        data_fim = datetime.now()
        duracao = (data_fim - self.inicio_gravacao).total_seconds() if self.inicio_gravacao else 0

        if self.writer is not None:
            self.writer.release()
            self.writer = None

        tamanho_bytes = 0
        if self.caminho_arquivo_atual and os.path.exists(self.caminho_arquivo_atual):
            tamanho_bytes = os.path.getsize(self.caminho_arquivo_atual)

        observacao = self.entry_observacao.get().strip()
        pedido = self.entry_pedido.get().strip()

        self.db.inserir_video(
            {
                "pedido": pedido,
                "nome_arquivo": self.nome_arquivo_atual,
                "caminho_arquivo": self.caminho_arquivo_atual,
                "data_inicio": self.inicio_gravacao.strftime("%Y-%m-%d %H:%M:%S") if self.inicio_gravacao else "",
                "data_fim": data_fim.strftime("%Y-%m-%d %H:%M:%S"),
                "duracao_segundos": round(duracao, 2),
                "tamanho_bytes": tamanho_bytes,
                "largura": self.resolucao_gravacao[0],
                "altura": self.resolucao_gravacao[1],
                "fps": self.fps_gravacao,
                "origem_camera": self.entry_url.get().strip(),
                "status": "gravado",
                "observacoes": observacao,
                "existe_arquivo": 1,
                "excluido_em": None,
            }
        )

        self.status_var.set("Status: Gravação finalizada")
        self.label_status.configure(text_color="#1F618D")
        self.btn_iniciar.configure(state="normal")
        self.btn_parar.configure(state="disabled")
        self.entry_observacao.delete(0, "end")
        self.entry_pedido.delete(0, "end")
        self.entry_pedido.focus()

        self.sincronizar_com_pasta(mostrar_mensagem=False)

        messagebox.showinfo(
            "Sucesso",
            f"Vídeo salvo com sucesso.\n\nArquivo: {self.nome_arquivo_atual}\nDuração: {self.formatar_tempo(duracao)}\nTamanho: {self.formatar_tamanho(tamanho_bytes)}",
        )

    def excluir_video_selecionado(self):
        selecionado = self.tree.selection()
        if not selecionado:
            messagebox.showwarning("Aviso", "Selecione um vídeo na tabela para excluir.")
            return

        item = self.tree.item(selecionado[0])
        video_id = item["values"][0]
        registro = self.db.obter_video_por_id(video_id)
        if not registro:
            messagebox.showerror("Erro", "Registro não encontrado no banco de dados.")
            return

        _, pedido, nome_arquivo, caminho_arquivo, status, existe_arquivo = registro
        if status == "excluido" or not existe_arquivo:
            messagebox.showinfo("Informação", "Este vídeo já está marcado como excluído.")
            return

        confirmar = messagebox.askyesno(
            "Confirmar exclusão",
            f"Deseja excluir o vídeo abaixo?\n\nID: {video_id}\nPedido: {pedido}\nArquivo: {nome_arquivo}",
        )
        if not confirmar:
            return

        if os.path.exists(caminho_arquivo):
            try:
                os.remove(caminho_arquivo)
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível excluir o arquivo físico.\n\nDetalhe: {e}")
                return

        self.db.marcar_como_excluido(video_id)
        self.sincronizar_com_pasta(mostrar_mensagem=False)
        messagebox.showinfo("Sucesso", "Vídeo excluído e registro atualizado no banco de dados.")

    def sincronizar_com_pasta(self, mostrar_mensagem=True):
        arquivos_fisicos = {str(arquivo.resolve()) for arquivo in self.pasta_videos.glob("*.avi")}
        registros = self.db.listar_videos(5000)
        alterados = 0

        for registro in registros:
            video_id = registro[0]
            caminho_arquivo = str(Path(registro[10]).resolve())
            existe_no_banco = registro[9]
            status = registro[8]
            existe_no_disco = caminho_arquivo in arquivos_fisicos

            if existe_no_disco and not existe_no_banco:
                self.db.atualizar_presenca_arquivo(video_id, 1, status="gravado")
                alterados += 1
            elif not existe_no_disco and existe_no_banco:
                novo_status = "excluido" if status != "excluido" else status
                self.db.atualizar_presenca_arquivo(video_id, 0, status=novo_status)
                alterados += 1

        self.atualizar_dashboard()
        self.atualizar_tabela()

        if mostrar_mensagem:
            total_pasta = len(arquivos_fisicos)
            messagebox.showinfo(
                "Sincronização concluída",
                f"Sincronização finalizada com sucesso.\n\nVídeos encontrados na pasta: {total_pasta}\nRegistros ajustados no banco: {alterados}",
            )

    def atualizar_preview(self):
        frame = self.camera.get_frame()
        if frame is not None:
            self.frame_atual = frame.copy()

            if self.gravando and self.writer is not None:
                self.writer.write(frame)

            largura_frame = max(self.preview_frame.winfo_width() - 32, 420)
            altura_frame = max(self.preview_frame.winfo_height() - 70, 260)
            proporcao = min(largura_frame / frame.shape[1], altura_frame / frame.shape[0])
            nova_largura = max(320, int(frame.shape[1] * proporcao))
            nova_altura = max(180, int(frame.shape[0] * proporcao))

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_rgb = cv2.resize(frame_rgb, (nova_largura, nova_altura))
            img = Image.fromarray(frame_rgb)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(nova_largura, nova_altura))
            self.label_video.configure(image=ctk_img, text="")
            self.label_video.image = ctk_img

        self.root.after(40, self.atualizar_preview)

    def atualizar_cronometro(self):
        if self.gravando and self.inicio_gravacao is not None:
            duracao = (datetime.now() - self.inicio_gravacao).total_seconds()
            self.cronometro_var.set(f"Tempo de gravação: {self.formatar_tempo(duracao)}")
        else:
            self.cronometro_var.set("Tempo de gravação: 00:00")

        self.root.after(300, self.atualizar_cronometro)

    def atualizar_dashboard(self):
        metricas = self.db.obter_metricas()
        total_fisico = len(list(self.pasta_videos.glob("*.avi")))

        self.card_total_videos.configure(text=str(total_fisico))
        self.card_total_pedidos.configure(text=str(metricas["total_pedidos"]))
        self.card_max.configure(text=self.formatar_tempo(metricas["max_duracao"]))
        self.card_media.configure(text=self.formatar_tempo(metricas["media_duracao"]))
        self.total_armazenado_var.set(f"Armazenamento total: {self.formatar_tamanho(metricas['total_armazenado'])}")
        self.excluidos_var.set(f"Vídeos excluídos: {metricas['total_excluidos']}")

    def atualizar_tabela(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        dados = self.db.listar_videos(200)
        for item in dados:
            vid_id, pedido, nome, data_inicio, duracao, tamanho, largura, altura, status, existe_arquivo, _ = item
            status_texto = "gravado" if existe_arquivo else "excluído"
            self.tree.insert(
                "",
                "end",
                values=(
                    vid_id,
                    pedido,
                    data_inicio,
                    self.formatar_tempo(duracao),
                    self.formatar_tamanho(tamanho),
                    f"{largura}x{altura}",
                    status_texto,
                ),
            )

    def on_tree_select(self, _event=None):
        selecionado = self.tree.selection()
        if not selecionado:
            self.selecao_var.set("ID selecionado: nenhum")
            return
        item = self.tree.item(selecionado[0])
        valores = item["values"]
        if valores:
            self.selecao_var.set(f"ID selecionado: {valores[0]} | Pedido: {valores[1]}")

    @staticmethod
    def formatar_tempo(segundos):
        try:
            segundos = int(round(float(segundos)))
        except (TypeError, ValueError):
            segundos = 0
        minutos = segundos // 60
        resto = segundos % 60
        horas = minutos // 60
        minutos = minutos % 60
        if horas > 0:
            return f"{horas:02d}:{minutos:02d}:{resto:02d}"
        return f"{minutos:02d}:{resto:02d}"

    @staticmethod
    def formatar_tamanho(bytes_valor):
        try:
            tamanho = float(bytes_valor)
        except (TypeError, ValueError):
            return "0 B"

        unidades = ["B", "KB", "MB", "GB"]
        indice = 0
        while tamanho >= 1024 and indice < len(unidades) - 1:
            tamanho /= 1024
            indice += 1
        return f"{tamanho:.1f} {unidades[indice]}"

    def fechar_app(self):
        try:
            if self.writer is not None:
                self.writer.release()

            self.camera.parar()

            self.serial_running = False
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.close()
        finally:
            self.root.destroy()


if __name__ == "__main__":
    root = ctk.CTk()
    app = AppCameraIP(root)
    root.mainloop()
